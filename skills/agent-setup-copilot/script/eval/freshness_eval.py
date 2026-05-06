#!/usr/bin/env python3
"""
Phase G — Freshness Eval

온톨로지 인스턴스 데이터의 신선도를 평가한다.
신선도는 각 엔트리의 날짜 메타데이터 필드를 기준으로 측정한다.

지원하는 날짜 필드 (우선순위 순):
  1. updated_at      — 명시적 갱신 날짜
  2. last_verified   — 마지막 검증 날짜
  3. released_at     — 출시일 (fallback: 데이터 최신성 하한선)
  4. 없음            — UNVERIFIABLE (날짜 메타데이터 추가 필요)

freshness 기준:
  FRESH        < 90일
  AGING        90–180일
  STALE        > 180일
  UNVERIFIABLE 날짜 필드 없음

사용:
  python3 eval/freshness_eval.py
  python3 eval/freshness_eval.py --instances-dir ../../agent-setup-ontology/instances
  python3 eval/freshness_eval.py --max-age-days 120 --strict
  python3 eval/freshness_eval.py --section models
  python3 eval/freshness_eval.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

# ── 경로 설정 ──────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent
_DEFAULT_INSTANCES = (
    _SCRIPT_DIR.parent.parent.parent.parent.parent
    / "agent-setup-ontology" / "instances"
)

# ── 상수 ──────────────────────────────────────────────────────

DATE_FIELDS = ("updated_at", "last_verified", "released_at")

THRESHOLDS = {
    "fresh":  90,    # 일
    "aging":  180,
    # > 180 = STALE
}

SECTION_FILES: dict[str, str] = {
    "devices":        "device.yaml",
    "models":         "model.yaml",
    "frameworks":     "framework.yaml",
    "use_cases":      "use_case.yaml",
    "api_services":   "api_service.yaml",
    "components":     "component.yaml",
    "repos":          "repo.yaml",
    "setup_profiles": "setup_profile.yaml",
}

# ── 헬퍼 ──────────────────────────────────────────────────────

def _parse_date(value: Any) -> date | None:
    """날짜 문자열 / date 객체 파싱. 실패 시 None."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m"):
            try:
                return datetime.strptime(value[:len(fmt.replace("%Y", "0000").replace("%m", "00").replace("%d", "00"))], fmt).date()
            except ValueError:
                continue
        # ISO-8601 fallback
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _extract_date(entry: dict) -> tuple[str | None, date | None]:
    """엔트리에서 가장 우선순위 높은 날짜 필드 추출.
    Returns (field_name, date_value)."""
    for field in DATE_FIELDS:
        raw = entry.get(field)
        if raw is not None:
            parsed = _parse_date(raw)
            if parsed:
                return field, parsed
    return None, None


def _age_days(d: date, today: date) -> int:
    return (today - d).days


def _freshness_label(age_days: int) -> str:
    if age_days < THRESHOLDS["fresh"]:
        return "FRESH"
    if age_days < THRESHOLDS["aging"]:
        return "AGING"
    return "STALE"


# ── 로딩 ──────────────────────────────────────────────────────

def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_section(instances_dir: Path, section: str) -> list[dict]:
    fname = SECTION_FILES.get(section)
    if not fname:
        return []
    fpath = instances_dir / fname
    if not fpath.exists():
        return []
    raw = _read_yaml(fpath)
    return raw.get(section, [])


# ── 평가 ──────────────────────────────────────────────────────

def eval_section(
    section: str,
    entries: list[dict],
    today: date,
    max_age_days: int,
) -> list[dict]:
    """섹션 내 모든 엔트리의 freshness 평가."""
    results = []
    for entry in entries:
        entry_id = entry.get("id", "(no-id)")
        label = entry.get("label", entry_id)
        field, ref_date = _extract_date(entry)

        if ref_date is None:
            results.append({
                "section": section,
                "id": entry_id,
                "label": label,
                "status": "UNVERIFIABLE",
                "field": None,
                "date": None,
                "age_days": None,
                "note": "No date metadata. Add 'updated_at' or 'last_verified'.",
            })
            continue

        age = _age_days(ref_date, today)
        status = _freshness_label(age) if age <= max_age_days else "STALE"
        # override: explicit STALE if beyond custom threshold
        if age > max_age_days:
            status = "STALE"

        results.append({
            "section": section,
            "id": entry_id,
            "label": label,
            "status": status,
            "field": field,
            "date": str(ref_date),
            "age_days": age,
            "note": None,
        })
    return results


def run_eval(
    instances_dir: Path,
    sections: list[str] | None,
    max_age_days: int,
    today: date | None = None,
) -> list[dict]:
    today = today or date.today()
    target_sections = sections or list(SECTION_FILES.keys())
    all_results: list[dict] = []

    for section in target_sections:
        entries = load_section(instances_dir, section)
        if not entries:
            continue
        results = eval_section(section, entries, today, max_age_days)
        all_results.extend(results)

    return all_results


# ── 리포트 ────────────────────────────────────────────────────

def print_report(
    results: list[dict],
    max_age_days: int,
    show_fresh: bool = False,
) -> None:
    by_status: dict[str, list[dict]] = {
        "STALE": [], "AGING": [], "UNVERIFIABLE": [], "FRESH": []
    }
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    print(f"\n📅 Freshness Eval (max_age={max_age_days}d, today={date.today()})")
    print(f"   Total entries: {len(results)}")
    for status in ("STALE", "AGING", "UNVERIFIABLE", "FRESH"):
        items = by_status[status]
        if items:
            print(f"   {status}: {len(items)}")

    if by_status["STALE"]:
        print(f"\n❌ STALE (> {max_age_days} days):")
        for r in by_status["STALE"]:
            print(f"   [{r['section']}] {r['id']:<30} age={r['age_days']}d  ref={r['date']} ({r['field']})")

    if by_status["AGING"]:
        print(f"\n⚠  AGING ({THRESHOLDS['fresh']}–{max_age_days} days):")
        for r in by_status["AGING"]:
            print(f"   [{r['section']}] {r['id']:<30} age={r['age_days']}d  ref={r['date']} ({r['field']})")

    if by_status["UNVERIFIABLE"]:
        print(f"\n🔲 UNVERIFIABLE (no date metadata):")
        for r in by_status["UNVERIFIABLE"]:
            print(f"   [{r['section']}] {r['id']:<30} → {r['note']}")

    if show_fresh and by_status["FRESH"]:
        print(f"\n✅ FRESH (< {THRESHOLDS['fresh']} days):")
        for r in by_status["FRESH"]:
            print(f"   [{r['section']}] {r['id']:<30} age={r['age_days']}d")

    # 전체 현황 한 줄 요약
    stale_count = len(by_status["STALE"]) + len(by_status["UNVERIFIABLE"])
    print(f"\n{'❌' if stale_count else '✅'} Summary: "
          f"{len(by_status['STALE'])} stale, "
          f"{len(by_status['AGING'])} aging, "
          f"{len(by_status['UNVERIFIABLE'])} unverifiable, "
          f"{len(by_status['FRESH'])} fresh")


# ── CLI ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase G — Ontology Freshness Eval"
    )
    parser.add_argument(
        "--instances-dir", type=Path, default=_DEFAULT_INSTANCES,
        help=f"instances/ 디렉토리 경로 (default: {_DEFAULT_INSTANCES})"
    )
    parser.add_argument(
        "--max-age-days", type=int, default=THRESHOLDS["aging"],
        help="이 기간(일) 초과 시 STALE (default: 180)"
    )
    parser.add_argument(
        "--section", nargs="+", choices=list(SECTION_FILES.keys()),
        help="평가할 섹션 (미지정 시 전체)"
    )
    parser.add_argument(
        "--show-fresh", action="store_true",
        help="FRESH 엔트리도 출력"
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="결과를 JSON으로 출력"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="STALE 또는 UNVERIFIABLE 있으면 exit 1"
    )
    args = parser.parse_args()

    if not args.instances_dir.exists():
        print(f"ERROR: instances-dir not found: {args.instances_dir}", file=sys.stderr)
        print("  --instances-dir 로 경로를 지정하거나, "
              "agent-setup-ontology 로컬 경로를 확인하세요.")
        sys.exit(1)

    results = run_eval(
        instances_dir=args.instances_dir,
        sections=args.section,
        max_age_days=args.max_age_days,
    )

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print_report(results, args.max_age_days, show_fresh=args.show_fresh)

    if args.strict:
        problem = any(r["status"] in ("STALE", "UNVERIFIABLE") for r in results)
        if problem:
            sys.exit(1)


if __name__ == "__main__":
    main()
