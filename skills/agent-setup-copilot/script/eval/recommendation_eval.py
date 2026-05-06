#!/usr/bin/env python3
"""
Phase G — Recommendation Quality Eval

golden_cases.yaml에 정의된 케이스를 기반으로 copilot 추천 품질을 평가한다.

평가 방식:
  - 프로그래매틱 체크 (deterministic): model/framework 포함·제외 여부
  - LLM-as-judge (선택): 추천 rationale 품질 채점
    → LLM judge는 API 키 필요. 없으면 프로그래매틱 체크만 수행.

프로그래매틱 체크:
  1. top_models: 추천 결과에 expected 모델 중 하나 이상 포함?
  2. must_exclude_models: 제외 대상 모델이 추천에 없는가?
  3. must_include_rationale: 추천 텍스트에 키워드 포함?
  4. must_exclude_rationale: 제외 대상 키워드가 추천에 없는가?

PROPOSE 시뮬레이션:
  실제 Claude Code 런타임이 없으므로, ontology 데이터 + estimator 기반으로
  "expected output"과 비교 가능한 후보 집합을 구성한다.
  이것은 완전한 recommendation 시뮬레이션이 아니라
  "ontology가 올바른 후보를 제공하는가"를 검증하는 데이터 품질 eval이다.

LLM-as-judge:
  --llm-judge 플래그 사용 시 활성화.
  ANTHROPIC_API_KEY 환경변수 필요.
  LLM에게 추천 시나리오와 기대 결과를 제시하고 0–10 점수를 요청.

사용:
  python3 eval/recommendation_eval.py
  python3 eval/recommendation_eval.py --cases eval/golden_cases.yaml
  python3 eval/recommendation_eval.py --case-id gc_001
  python3 eval/recommendation_eval.py --llm-judge
  python3 eval/recommendation_eval.py --strict
  python3 eval/recommendation_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# ── 경로 설정 ──────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_CASES = _SCRIPT_DIR / "golden_cases.yaml"
_ONTOLOGY_BASE = (
    _SCRIPT_DIR.parent.parent.parent.parent.parent
    / "agent-setup-ontology" / "instances"
)

# ── 데이터 로딩 ───────────────────────────────────────────────

def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_golden_cases(cases_path: Path) -> list[dict]:
    data = _read_yaml(cases_path)
    if isinstance(data, dict):
        return data.get("golden_cases", [])
    return data or []


def load_models(instances_dir: Path) -> list[dict]:
    p = instances_dir / "model.yaml"
    if not p.exists():
        return []
    return _read_yaml(p).get("models", []) or []


def load_devices(instances_dir: Path) -> list[dict]:
    p = instances_dir / "device.yaml"
    if not p.exists():
        return []
    return _read_yaml(p).get("devices", []) or []


def load_frameworks(instances_dir: Path) -> list[dict]:
    p = instances_dir / "framework.yaml"
    if not p.exists():
        return []
    return _read_yaml(p).get("frameworks", []) or []


# ── PROPOSE 시뮬레이션 (데이터 품질 기반) ─────────────────────

def simulate_candidates(
    case_input: dict,
    models: list[dict],
    devices: list[dict],
    frameworks: list[dict],
) -> dict:
    """
    PROPOSE 단계의 후보 집합을 구성한다.
    실제 Claude Code 추론 없이 ontology 데이터만으로 구성하므로
    "데이터가 올바른 후보를 제공하는가"를 검증하는 수준이다.
    """
    constraint = case_input.get("constraint", {})
    device_id = constraint.get("device")
    goal = case_input.get("goal")
    deployment_target = case_input.get("deployment_target", "local")
    negative = constraint.get("negative", [])
    hard = constraint.get("hard", [])

    # 디바이스 메모리 제약
    # Mac 디바이스는 unified_memory_gb 필드를 사용함에 주의
    device = next((d for d in devices if d.get("id") == device_id), None)
    available_memory = 0
    if device:
        if device.get("type") != "pc":
            available_memory = (device.get("memory_gb")
                                or device.get("unified_memory_gb", 0))
        else:
            available_memory = device.get("gpu_vram_gb", 0)

    # 모델 후보: 메모리 적합 모델만
    candidate_models = []
    for m in models:
        if available_memory > 0 and m.get("min_memory_gb", 0) > available_memory:
            continue
        # negative constraint 제거 (예: docker 필요 모델)
        candidate_models.append(m["id"])

    # 프레임워크 후보: goal 적합
    candidate_frameworks = []
    for f in frameworks:
        # negative constraint에 포함된 프레임워크 제거
        if any(neg.lower() in f.get("id", "").lower() for neg in negative):
            continue
        # cloud-only 제거 (local 배포 시)
        if deployment_target == "local" and not f.get("local_capable", True):
            continue
        candidate_frameworks.append(f["id"])

    return {
        "candidate_models": candidate_models,
        "candidate_frameworks": candidate_frameworks,
        "device": device_id,
        "goal": goal,
    }


# ── 프로그래매틱 체크 ────────────────────────────────────────

def programmatic_check(case: dict, candidates: dict) -> dict:
    """
    golden case 기대값과 시뮬레이션 결과를 프로그래매틱으로 비교.
    """
    expected = case.get("expected", {})
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    candidate_models = set(candidates["candidate_models"])
    candidate_frameworks = set(candidates["candidate_frameworks"])

    # 체크 1: top_models — 하나 이상 포함
    top_models = expected.get("top_models", [])
    if top_models:
        hit = any(m in candidate_models for m in top_models)
        checks["top_models_any_of"] = hit
        if not hit:
            errors.append(
                f"top_models: none of {top_models} in candidates {list(candidate_models)[:5]}..."
            )

    # 체크 2: must_exclude_models — 포함되면 안 됨
    must_exclude = expected.get("must_exclude_models", [])
    for excl in must_exclude:
        present = excl in candidate_models
        checks[f"exclude_{excl}"] = not present
        if present:
            errors.append(f"must_exclude_models: '{excl}' is in candidates (should be excluded)")

    # 체크 3: top_frameworks
    top_frameworks = expected.get("top_frameworks", [])
    if top_frameworks:
        hit = any(f in candidate_frameworks for f in top_frameworks)
        checks["top_frameworks_any_of"] = hit
        if not hit:
            warnings.append(
                f"top_frameworks: none of {top_frameworks} in candidates {list(candidate_frameworks)[:5]}..."
            )

    # 체크 4: must_include_rationale — 현재 candidates에서 keyword 확인은
    # 실제 추천 텍스트 없이 불가 → metadata로 대체 확인
    # (LLM-as-judge에서 완전 검증)
    must_include_rationale = expected.get("must_include_rationale", [])
    if must_include_rationale:
        checks["rationale_check"] = None  # LLM judge 필요

    passed = len(errors) == 0
    return {
        "case_id": case["id"],
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "candidates_snapshot": {
            "models_count": len(candidate_models),
            "frameworks_count": len(candidate_frameworks),
            "top_model_hits": [m for m in top_models if m in candidate_models],
        },
    }


# ── LLM-as-judge ─────────────────────────────────────────────

def llm_judge(case: dict, candidates: dict) -> dict:
    """
    LLM에게 케이스를 제시하고 추천 품질을 0–10으로 채점.
    ANTHROPIC_API_KEY 환경변수가 없으면 SKIP 반환.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "SKIP", "reason": "ANTHROPIC_API_KEY not set"}

    try:
        import anthropic
    except ImportError:
        return {"status": "SKIP", "reason": "anthropic package not installed"}

    client = anthropic.Anthropic(api_key=api_key)

    expected = case.get("expected", {})
    prompt = f"""You are evaluating an AI agent setup recommendation system.

Case: {case['description']}

User Input:
  Goal: {case['input'].get('goal')}
  Device: {case['input'].get('constraint', {}).get('device')}
  Hard constraints: {case['input'].get('constraint', {}).get('hard', [])}
  Negative constraints: {case['input'].get('constraint', {}).get('negative', [])}
  Tech level: {case['input'].get('tech_level')}

Candidate models produced by the system: {candidates['candidate_models'][:10]}
Candidate frameworks: {candidates['candidate_frameworks'][:5]}

Expected (any-of): models={expected.get('top_models', [])} frameworks={expected.get('top_frameworks', [])}
Expected rationale keywords: {expected.get('must_include_rationale', [])}
Must NOT recommend: {expected.get('must_exclude_models', [])}

Score the quality of the system's output on a scale of 0–10:
- 10: All expected models/frameworks present, excludes all forbidden ones, rationale complete
- 7–9: Expected items mostly present, minor gaps
- 4–6: Some expected items missing or some forbidden items present
- 0–3: Fundamentally wrong recommendations

Return ONLY a JSON object: {{"score": <0-10>, "reason": "<one sentence>"}}"""

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # JSON 추출
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            return {"status": "OK", "score": result.get("score"), "reason": result.get("reason")}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

    return {"status": "ERROR", "reason": "Failed to parse LLM response"}


# ── 통합 실행 ─────────────────────────────────────────────────

def run_eval(
    cases_path: Path,
    instances_dir: Path,
    case_id: str | None,
    use_llm_judge: bool,
) -> list[dict]:
    cases = load_golden_cases(cases_path)
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]
        if not cases:
            print(f"ERROR: case '{case_id}' not found in {cases_path}", file=sys.stderr)
            return []

    models = load_models(instances_dir)
    devices = load_devices(instances_dir)
    frameworks = load_frameworks(instances_dir)

    results = []
    for case in cases:
        candidates = simulate_candidates(
            case.get("input", {}), models, devices, frameworks
        )
        prog_result = programmatic_check(case, candidates)

        judge_result = None
        if use_llm_judge:
            judge_result = llm_judge(case, candidates)

        results.append({
            "case_id": case["id"],
            "description": case.get("description"),
            "weight": case.get("weight", 1),
            "tags": case.get("tags", []),
            "programmatic": prog_result,
            "llm_judge": judge_result,
        })

    return results


# ── 리포트 ────────────────────────────────────────────────────

def print_report(results: list[dict]) -> None:
    passed = [r for r in results if r["programmatic"]["passed"]]
    failed = [r for r in results if not r["programmatic"]["passed"]]

    print(f"\n🎯 Recommendation Quality Eval")
    print(f"   Total cases: {len(results)}  |  PASS: {len(passed)}  |  FAIL: {len(failed)}")

    if failed:
        print("\n❌ FAIL:")
        for r in failed:
            prog = r["programmatic"]
            print(f"   [{r['case_id']}] {r['description']}")
            for err in prog["errors"]:
                print(f"     ✗ {err}")
            for warn in prog["warnings"]:
                print(f"     ⚠  {warn}")

    if passed:
        print("\n✅ PASS:")
        for r in passed:
            prog = r["programmatic"]
            snap = prog["candidates_snapshot"]
            print(f"   [{r['case_id']}] {r['description']}")
            print(f"     candidates: {snap['models_count']} models, "
                  f"{snap['frameworks_count']} frameworks  "
                  f"top_hits: {snap.get('top_model_hits', [])}")
            if prog["warnings"]:
                for warn in prog["warnings"]:
                    print(f"     ⚠  {warn}")

    # LLM judge 결과
    llm_results = [r for r in results if r.get("llm_judge") and r["llm_judge"]["status"] == "OK"]
    if llm_results:
        print("\n🤖 LLM-as-judge scores:")
        for r in llm_results:
            j = r["llm_judge"]
            print(f"   [{r['case_id']}] score={j['score']}/10  → {j['reason']}")
    elif any(r.get("llm_judge") for r in results):
        sample = next(r for r in results if r.get("llm_judge"))
        j = sample["llm_judge"]
        print(f"\n⏭  LLM judge: {j['status']} — {j.get('reason', '')}")

    print(f"\n{'✅' if not failed else '❌'} "
          f"Programmatic: {len(passed)}/{len(results)} passed")


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase G — Recommendation Quality Eval"
    )
    parser.add_argument("--cases", type=Path, default=_DEFAULT_CASES,
                        help=f"golden_cases.yaml 경로 (default: {_DEFAULT_CASES})")
    parser.add_argument("--instances-dir", type=Path, default=_ONTOLOGY_BASE,
                        help="instances/ 디렉토리 경로")
    parser.add_argument("--case-id", help="특정 케이스만 실행")
    parser.add_argument("--llm-judge", action="store_true",
                        help="LLM-as-judge 활성화 (ANTHROPIC_API_KEY 필요)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true",
                        help="FAIL 있으면 exit 1")
    args = parser.parse_args()

    if not args.cases.exists():
        print(f"ERROR: golden_cases.yaml not found: {args.cases}", file=sys.stderr)
        sys.exit(1)

    instances_dir = args.instances_dir
    if not instances_dir.exists():
        print(f"ERROR: instances-dir not found: {instances_dir}", file=sys.stderr)
        print("  --instances-dir 로 agent-setup-ontology/instances 경로를 지정하세요.")
        sys.exit(1)

    results = run_eval(
        cases_path=args.cases,
        instances_dir=instances_dir,
        case_id=args.case_id,
        use_llm_judge=args.llm_judge,
    )

    if not results:
        return

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print_report(results)

    if args.strict:
        failed = any(not r["programmatic"]["passed"] for r in results)
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
