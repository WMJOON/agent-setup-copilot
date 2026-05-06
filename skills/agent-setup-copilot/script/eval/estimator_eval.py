#!/usr/bin/env python3
"""
Phase G — Estimator Accuracy Eval

estimator.py의 예측 t/s를 speed_note에 명시된 실측 범위와 비교해
정확도를 평가한다.

speed_note 파싱:
  "~18-25 t/s (M4 base 32GB)"   → range=(18,25), device_hint="M4 base 32GB"
  "~20-35 t/s (M-series 16GB)"  → range=(20,35), device_hint="M-series 16GB"
  "~25 t/s on M4 32GB"          → range=(25,25), device_hint="M4 32GB"

device_hint → device_id 매핑은 HINT_DEVICE_MAP으로 관리.
매핑 없으면 디바이스 레코드의 첫 번째 가장 가까운 메모리 크기로 fallback.

정확도 기준:
  PASS     오차율 < 20%  (예측이 실측 범위 midpoint 기준)
  WARNING  오차율 20–40%
  FAIL     오차율 > 40%  또는 예측이 범위를 완전히 벗어남

선행 조건:
  instances/model.yaml — speed_note 필드 (현재 있음)
  instances/device.yaml — memory_bandwidth_gbs 필드 (현재 있음)

사용:
  python3 eval/estimator_eval.py
  python3 eval/estimator_eval.py --device mac_mini_m4_32gb --model qwen3.5:35b-a3b
  python3 eval/estimator_eval.py --all-pairs
  python3 eval/estimator_eval.py --strict
  python3 eval/estimator_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ── 경로 설정 ──────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent
_ONTOLOGY_BASE = (
    _SCRIPT_DIR.parent.parent.parent.parent.parent
    / "agent-setup-ontology" / "instances"
)

# estimator.py 가져오기
sys.path.insert(0, str(_SCRIPT_DIR.parent))
try:
    from estimator import (
        estimate_tps, effective_params, fits_in_memory,
        BYTES_PER_PARAM, MOE_FACTOR, KV_CACHE_GB, VRAM_HEADROOM,
    )
    _ESTIMATOR_AVAILABLE = True
except ImportError:
    _ESTIMATOR_AVAILABLE = False

# ── 상수 ──────────────────────────────────────────────────────

PASS_THRESHOLD    = 0.20   # 오차율 20% 이하 → PASS
WARNING_THRESHOLD = 0.40   # 오차율 40% 이하 → WARNING, 초과 → FAIL

# speed_note의 device_hint 문자열 → device_id 매핑
# 새 디바이스 추가 시 이 목록 확장
HINT_DEVICE_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"M4\s*(?:base)?\s*32GB", re.I),   "mac_mini_m4_32gb"),
    (re.compile(r"M4\s*Pro\s*48GB", re.I),          "mac_studio_m4_pro_48gb"),
    (re.compile(r"M4\s*Max\s*64GB", re.I),          "mac_studio_m4_max_64gb"),
    (re.compile(r"M-series\s*16GB", re.I),           "macbook_16gb"),
    (re.compile(r"M-series\s*32GB", re.I),           "mac_mini_m4_32gb"),
    (re.compile(r"M[123]\s*16GB", re.I),             "macbook_16gb"),
    (re.compile(r"M[123]\s*32GB", re.I),             "macbook_pro_32gb"),
    (re.compile(r"RTX\s*4090", re.I),               "rtx_4090_pc"),
    (re.compile(r"RTX\s*3090", re.I),               "rtx_3090_pc"),
]

# ── speed_note 파싱 ───────────────────────────────────────────

_TPS_RANGE_RE = re.compile(
    r"[~≈]?\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*t/s",
    re.I,
)
_TPS_SINGLE_RE = re.compile(
    r"[~≈]?\s*(\d+(?:\.\d+)?)\s*t/s",
    re.I,
)
_DEVICE_HINT_RE = re.compile(r"\(([^)]+)\)")


def parse_speed_note(speed_note: str) -> dict | None:
    """
    speed_note 문자열에서 t/s 범위와 device_hint를 추출.
    Returns None if unparseable.
    """
    if not speed_note:
        return None

    tps_range = None
    m = _TPS_RANGE_RE.search(speed_note)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        tps_range = (lo, hi)
    else:
        m = _TPS_SINGLE_RE.search(speed_note)
        if m:
            v = float(m.group(1))
            tps_range = (v, v)

    if not tps_range:
        return None

    device_hint = None
    mh = _DEVICE_HINT_RE.search(speed_note)
    if mh:
        device_hint = mh.group(1).strip()

    return {
        "tps_range": tps_range,
        "midpoint": (tps_range[0] + tps_range[1]) / 2,
        "device_hint": device_hint,
    }


def hint_to_device_id(hint: str | None) -> str | None:
    """device_hint 문자열 → device_id (HINT_DEVICE_MAP 기반)."""
    if not hint:
        return None
    for pattern, device_id in HINT_DEVICE_MAP:
        if pattern.search(hint):
            return device_id
    return None


# ── 데이터 로딩 ───────────────────────────────────────────────

def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_models(instances_dir: Path) -> list[dict]:
    p = instances_dir / "model.yaml"
    if not p.exists():
        return []
    return _read_yaml(p).get("models", [])


def load_devices(instances_dir: Path) -> list[dict]:
    p = instances_dir / "device.yaml"
    if not p.exists():
        return []
    return _read_yaml(p).get("devices", [])


def find_device(devices: list[dict], device_id: str) -> dict | None:
    return next((d for d in devices if d["id"] == device_id), None)


def find_model(models: list[dict], model_id: str) -> dict | None:
    return next((m for m in models if m["id"] == model_id), None)


# ── 예측 계산 ─────────────────────────────────────────────────

def _predict_tps(device: dict, model: dict) -> float | None:
    """estimator 공식으로 t/s 예측."""
    if not _ESTIMATOR_AVAILABLE:
        # estimator import 실패 시 직접 계산
        bw = device.get("memory_bandwidth_gbs", 0)
        if not bw:
            return None
        if model.get("type") == "MoE":
            active = model.get("active_params_b", model["params_b"] * 0.1)
            eff = active * MOE_FACTOR if _ESTIMATOR_AVAILABLE else active * 3.5
        else:
            eff = model["params_b"]
        bp = BYTES_PER_PARAM if _ESTIMATOR_AVAILABLE else 0.5625
        return round(bw / (eff * bp), 1) if eff > 0 else None

    bw = device.get("memory_bandwidth_gbs", 0)
    if not bw:
        return None

    # 메모리 fit 확인
    # unified_memory_gb (Mac) → memory_gb fallback 처리
    # 참고: instances/device.yaml은 unified_memory_gb를 사용하고 있음.
    # estimator.py의 bundle은 sync_ontology_bundle.py가 memory_gb로 정규화할 수 있음.
    # eval에서는 두 필드 모두 시도.
    if device.get("type") != "pc":
        avail = (device.get("memory_gb")
                 or device.get("unified_memory_gb", 0))
    else:
        avail = device.get("gpu_vram_gb", 0)

    fits, _, _ = fits_in_memory(avail, model)
    effective_bw = bw if fits else 30.0
    return estimate_tps(effective_bw, model)


# ── Eval 핵심 ─────────────────────────────────────────────────

def eval_pair(device: dict, model: dict) -> dict:
    """device-model 한 쌍에 대한 정확도 평가."""
    speed_note = model.get("speed_note", "")
    parsed = parse_speed_note(speed_note)

    result_base = {
        "device_id": device["id"],
        "model_id": model["id"],
        "speed_note": speed_note,
    }

    if not parsed:
        return {**result_base, "status": "NO_BENCHMARK", "note": "speed_note 파싱 불가"}

    # device_hint가 이 디바이스를 가리키는지 확인
    hinted_device_id = hint_to_device_id(parsed["device_hint"])
    if hinted_device_id and hinted_device_id != device["id"]:
        return {
            **result_base,
            "status": "SKIP",
            "note": f"speed_note는 {hinted_device_id}용 — 이 디바이스와 무관",
        }

    predicted = _predict_tps(device, model)
    if predicted is None:
        return {**result_base, "status": "NO_BANDWIDTH", "note": "device bandwidth 없음"}

    lo, hi = parsed["tps_range"]
    midpoint = parsed["midpoint"]
    error_rate = abs(predicted - midpoint) / midpoint if midpoint > 0 else 0
    in_range = lo <= predicted <= hi

    if error_rate < PASS_THRESHOLD or in_range:
        status = "PASS"
    elif error_rate < WARNING_THRESHOLD:
        status = "WARNING"
    else:
        status = "FAIL"

    return {
        **result_base,
        "status": status,
        "predicted_tps": predicted,
        "benchmark_range": [lo, hi],
        "benchmark_midpoint": midpoint,
        "error_rate": round(error_rate, 3),
        "in_range": in_range,
        "note": None,
    }


def run_eval(
    instances_dir: Path,
    device_id: str | None = None,
    model_id: str | None = None,
    all_pairs: bool = False,
) -> list[dict]:
    models = load_models(instances_dir)
    devices = load_devices(instances_dir)

    if not models or not devices:
        print("ERROR: model.yaml 또는 device.yaml을 로드할 수 없습니다.", file=sys.stderr)
        return []

    pairs: list[tuple[dict, dict]] = []

    if device_id and model_id:
        d = find_device(devices, device_id)
        m = find_model(models, model_id)
        if not d:
            print(f"ERROR: device '{device_id}' not found", file=sys.stderr)
            return []
        if not m:
            print(f"ERROR: model '{model_id}' not found", file=sys.stderr)
            return []
        pairs = [(d, m)]

    elif device_id:
        d = find_device(devices, device_id)
        if not d:
            print(f"ERROR: device '{device_id}' not found", file=sys.stderr)
            return []
        pairs = [(d, m) for m in models if m.get("speed_note")]

    elif model_id:
        m = find_model(models, model_id)
        if not m:
            print(f"ERROR: model '{model_id}' not found", file=sys.stderr)
            return []
        pairs = [(d, m) for d in devices if m.get("speed_note")]

    elif all_pairs:
        # speed_note가 있는 모델과 대역폭이 있는 디바이스의 전체 조합
        pairs = [
            (d, m)
            for m in models if m.get("speed_note")
            for d in devices if d.get("memory_bandwidth_gbs")
        ]
    else:
        # 기본: speed_note가 있는 모델 × device_hint 매핑 조합만
        for m in models:
            if not m.get("speed_note"):
                continue
            parsed = parse_speed_note(m["speed_note"])
            if not parsed:
                continue
            hinted_id = hint_to_device_id(parsed.get("device_hint"))
            if hinted_id:
                d = find_device(devices, hinted_id)
                if d:
                    pairs.append((d, m))

    return [eval_pair(d, m) for d, m in pairs]


# ── 리포트 ────────────────────────────────────────────────────

def print_report(results: list[dict]) -> None:
    by_status: dict[str, list[dict]] = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    evaluable = [r for r in results if r["status"] not in ("SKIP", "NO_BENCHMARK", "NO_BANDWIDTH")]
    skipped = [r for r in results if r["status"] in ("SKIP", "NO_BENCHMARK", "NO_BANDWIDTH")]

    print(f"\n📊 Estimator Accuracy Eval")
    print(f"   Total pairs evaluated: {len(evaluable)}  |  Skipped: {len(skipped)}")

    for status in ("PASS", "WARNING", "FAIL"):
        n = len(by_status.get(status, []))
        if n:
            print(f"   {status}: {n}")

    if by_status.get("FAIL"):
        print("\n❌ FAIL (error rate > 40%):")
        for r in by_status["FAIL"]:
            print(f"   {r['device_id']} × {r['model_id']}")
            print(f"     predicted={r['predicted_tps']} t/s  "
                  f"benchmark={r['benchmark_range']} (mid={r['benchmark_midpoint']})  "
                  f"error={r['error_rate']*100:.1f}%  in_range={r.get('in_range')}")

    if by_status.get("WARNING"):
        print("\n⚠  WARNING (error rate 20–40%):")
        for r in by_status["WARNING"]:
            print(f"   {r['device_id']} × {r['model_id']}")
            print(f"     predicted={r['predicted_tps']} t/s  "
                  f"benchmark={r['benchmark_range']}  "
                  f"error={r['error_rate']*100:.1f}%")

    if by_status.get("PASS"):
        print("\n✅ PASS:")
        for r in by_status["PASS"]:
            print(f"   {r['device_id']:<30} × {r['model_id']:<25}"
                  f" predicted={r['predicted_tps']} t/s  "
                  f"benchmark={r['benchmark_range']}")

    if skipped:
        print(f"\n⏭  Skipped ({len(skipped)}):")
        for r in skipped:
            print(f"   {r['device_id']} × {r['model_id']}: {r.get('note', r['status'])}")

    fail_count = len(by_status.get("FAIL", []))
    warn_count = len(by_status.get("WARNING", []))
    print(f"\n{'❌' if fail_count else ('⚠ ' if warn_count else '✅')} "
          f"Summary: {fail_count} fail, {warn_count} warning, "
          f"{len(by_status.get('PASS', []))} pass")


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase G — Estimator Accuracy Eval"
    )
    parser.add_argument("--instances-dir", type=Path, default=_DEFAULT_INSTANCES if '_DEFAULT_INSTANCES' in dir() else _ONTOLOGY_BASE,
                        help="instances/ 디렉토리 경로")
    parser.add_argument("--device", help="특정 device ID")
    parser.add_argument("--model", help="특정 model ID")
    parser.add_argument("--all-pairs", action="store_true",
                        help="속도 데이터 있는 모든 device-model 조합 평가")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true",
                        help="FAIL 있으면 exit 1")
    args = parser.parse_args()

    instances_dir = args.instances_dir
    if not instances_dir.exists():
        # fallback: 스크립트 위치 기반 탐색
        instances_dir = _ONTOLOGY_BASE
    if not instances_dir.exists():
        print(f"ERROR: instances-dir not found: {instances_dir}", file=sys.stderr)
        print("  --instances-dir 로 agent-setup-ontology/instances 경로를 지정하세요.")
        sys.exit(1)

    results = run_eval(
        instances_dir=instances_dir,
        device_id=args.device,
        model_id=args.model,
        all_pairs=args.all_pairs,
    )

    if not results:
        print("평가할 쌍이 없습니다. --all-pairs 또는 --device/--model 지정을 확인하세요.")
        return

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print_report(results)

    if args.strict:
        if any(r["status"] == "FAIL" for r in results):
            sys.exit(1)


# 경로 상수 보정
_DEFAULT_INSTANCES = _ONTOLOGY_BASE

if __name__ == "__main__":
    main()
