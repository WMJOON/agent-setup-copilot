#!/usr/bin/env python3
"""
agent-setup-copilot governance: 정식 온톨로지 검증기
Source of Truth: agent-setup-copilot/governance/scripts/validate.py

온톨로지 레포(local-agent-ontology)의 ontology-harness 스킬도
이 스크립트를 참조해 검증을 위임한다.

사용:
  # 소비자 레포에서 직접 실행
  python governance/scripts/validate.py --ontology path/to/ontology.yaml

  # CI 모드 (실패 시 exit 1)
  python governance/scripts/validate.py --ontology ontology.yaml --strict

  # 특정 ID 참조 위치 탐색
  python governance/scripts/validate.py --ontology ontology.yaml --find-refs qwen3.5:9b
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

# governance 디렉토리 기준
GOVERNANCE_DIR = Path(__file__).parent.parent
SCHEMA_PATH = GOVERNANCE_DIR / "schema.json"

# ── Contract definition (keep in sync with governance/GOVERNANCE.md) ──────────

ID_PATTERN = re.compile(r"^[a-z0-9_.:-]+$")

REQUIRED_FIELDS = {
    "use_cases":    ["id", "label", "description", "keywords", "min_memory_gb"],
    "devices":      ["id", "label", "type", "memory_gb", "tier", "max_model"],
    "models":       ["id", "label", "params_b", "type", "min_memory_gb", "quality", "tool_calling"],
    "frameworks":   ["id", "label", "kind", "complexity", "local_capable", "runtime_support"],
    "api_services": ["id", "label", "provider", "quality", "tool_calling", "pricing"],
    "components":   ["id", "label", "component_type", "inference_tier", "price_search_query"],
}

ENUM_CONTRACTS = {
    "devices": {
        "type":        {"macbook", "mac-mini", "mac-studio", "pc", "other"},
        "tier":        {"light", "standard", "standard-plus", "pro"},
        "portability": {"portable", "stationary"},
    },
    "models": {
        "type":    {"dense", "MoE"},
        "quality": {"light", "standard", "standard-plus", "pro"},
    },
    "frameworks": {
        "kind":       {"agent", "automation", "ui", "ide", "rag"},
        "complexity": {"low", "medium", "high"},
    },
}

RUNTIME_SUPPORT_ALLOWED = {"ollama", "openai", "anthropic", "huggingface", "litellm", "any"}
PROVIDER_ALLOWED = {"anthropic", "openai", "google", "mistral", "cohere", "other"}

# Cross-reference contract: (source_section, source_field, target_section)
CROSS_REF_CONTRACTS = [
    ("devices",      "supported_use_cases",   "use_cases"),
    ("devices",      "unsupported_use_cases",  "use_cases"),
    ("devices",      "max_model",              "models"),
    ("use_cases",    "recommended_models",     "models"),
    ("use_cases",    "recommended_frameworks", "frameworks"),
    ("api_services", "local_alternative",      "models"),     # api_service → model
]



# ── 검증 함수 ──────────────────────────────────────────────

class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(f"  ✗ {msg}")

    def warn(self, msg: str):
        self.warnings.append(f"  ⚠ {msg}")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def check_required_fields(ontology: dict, sections: list[str]) -> ValidationResult:
    result = ValidationResult()
    for section in sections:
        if section not in REQUIRED_FIELDS:
            continue
        required = REQUIRED_FIELDS[section]
        for i, item in enumerate(ontology.get(section, [])):
            item_id = item.get("id", f"[index {i}]")
            for field in required:
                if field not in item:
                    result.error(f"{section}[{item_id}]: 필수 필드 '{field}' 없음")
    return result


def check_id_uniqueness(ontology: dict, sections: list[str]) -> ValidationResult:
    result = ValidationResult()
    for section in sections:
        seen: set[str] = set()
        for item in ontology.get(section, []):
            item_id = item.get("id", "")
            if item_id in seen:
                result.error(f"{section}: ID '{item_id}' 중복")
            seen.add(item_id)
    return result


def check_id_naming(ontology: dict, sections: list[str]) -> ValidationResult:
    result = ValidationResult()
    for section in sections:
        for item in ontology.get(section, []):
            item_id = item.get("id", "")
            if not item_id:
                continue
            if not ID_PATTERN.match(item_id):
                result.error(
                    f"{section}[{item_id}]: ID에 허용되지 않는 문자 포함 "
                    f"(허용: a-z 0-9 _ . : -)"
                )
    return result


def check_enums(ontology: dict, sections: list[str]) -> ValidationResult:
    result = ValidationResult()
    for section in sections:
        contracts = ENUM_CONTRACTS.get(section, {})
        for item in ontology.get(section, []):
            item_id = item.get("id", "?")
            for field, allowed in contracts.items():
                val = item.get(field)
                if val is not None and val not in allowed:
                    result.error(
                        f"{section}[{item_id}].{field}: '{val}' not in allowed values "
                        f"({sorted(allowed)})"
                    )

            # frameworks.runtime_support — each element must be an allowed value
            if section == "frameworks":
                runtime = item.get("runtime_support")
                if isinstance(runtime, list):
                    for r in runtime:
                        if r not in RUNTIME_SUPPORT_ALLOWED:
                            result.error(
                                f"frameworks[{item_id}].runtime_support: '{r}' not allowed "
                                f"({sorted(RUNTIME_SUPPORT_ALLOWED)})"
                            )
    return result


def check_cross_refs(ontology: dict) -> ValidationResult:
    result = ValidationResult()

    # 섹션별 유효 ID 집합 구성
    valid_ids: dict[str, set] = {
        section: {item["id"] for item in ontology.get(section, []) if "id" in item}
        for section in ["use_cases", "devices", "models", "frameworks"]
    }

    for src_section, src_field, tgt_section in CROSS_REF_CONTRACTS:
        tgt_ids = valid_ids.get(tgt_section, set())

        for item in ontology.get(src_section, []):
            item_id = item.get("id", "?")
            val = item.get(src_field)

            if val is None:
                continue

            # 단일 값 또는 리스트 모두 처리
            refs = val if isinstance(val, list) else [val]

            for ref in refs:
                if ref == "all":
                    continue  # "all" 은 모든 use_case를 의미하는 특수값
                if ref not in tgt_ids:
                    result.error(
                        f"{src_section}[{item_id}].{src_field}: "
                        f"'{ref}' → {tgt_section}에 존재하지 않음"
                    )
    return result


def find_refs(ontology: dict, target_id: str) -> list[str]:
    """특정 ID가 참조되는 위치를 모두 반환"""
    locations = []
    for src_section, src_field, tgt_section in CROSS_REF_CONTRACTS:
        for item in ontology.get(src_section, []):
            item_id = item.get("id", "?")
            val = item.get(src_field)
            if val is None:
                continue
            refs = val if isinstance(val, list) else [val]
            if target_id in refs:
                locations.append(f"{src_section}[{item_id}].{src_field}")
    return locations


# ── 스키마 검증 (jsonschema 있을 때만) ──────────────────────

def check_json_schema(ontology: dict) -> ValidationResult:
    result = ValidationResult()
    try:
        import json
        import jsonschema
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        jsonschema.validate(ontology, schema)
    except ImportError:
        result.warn("jsonschema 미설치 — 스키마 검증 건너뜀 (pip install jsonschema)")
    except Exception as e:
        result.error(f"스키마 검증 실패: {e}")
    return result


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="agent-setup-copilot governance 검증기",
        epilog="governance Source of Truth: agent-setup-copilot/governance/",
    )
    parser.add_argument(
        "--ontology", metavar="PATH",
        default=None,
        help="검증할 ontology.yaml 경로 (기본: 현재 디렉토리의 ontology.yaml)",
    )
    parser.add_argument("--strict", action="store_true", help="실패 시 exit 1")
    parser.add_argument("--only-refs", action="store_true", help="교차 참조만 검증")
    parser.add_argument("--find-refs", metavar="ID", help="특정 ID 참조 위치 탐색")
    parser.add_argument("--section", metavar="SECTION", help="특정 섹션만 검증")
    args = parser.parse_args()

    ontology_path = Path(args.ontology) if args.ontology else Path("ontology.yaml")
    if not ontology_path.exists():
        print(f"✗ 파일 없음: {ontology_path}")
        sys.exit(1)

    with open(ontology_path, encoding="utf-8") as f:
        ontology = yaml.safe_load(f)

    sections = (
        [args.section] if args.section
        else ["use_cases", "devices", "models", "frameworks", "api_services", "components"]
    )

    # --find-refs 모드
    if args.find_refs:
        locations = find_refs(ontology, args.find_refs)
        if locations:
            print(f"\n'{args.find_refs}' 참조 위치 ({len(locations)}건):")
            for loc in locations:
                print(f"  → {loc}")
        else:
            print(f"\n'{args.find_refs}' 를 참조하는 항목이 없습니다.")
        return

    # 검증 실행
    all_errors: list[str] = []
    all_warnings: list[str] = []

    if args.only_refs:
        checks = [("교차 참조 정합성", check_cross_refs(ontology))]
    else:
        checks = [
            ("스키마 conformance",   check_json_schema(ontology)),
            ("필수 필드",            check_required_fields(ontology, sections)),
            ("ID 유일성",            check_id_uniqueness(ontology, sections)),
            ("ID 명명 규칙",         check_id_naming(ontology, sections)),
            ("Enum 값",              check_enums(ontology, sections)),
            ("교차 참조 정합성",     check_cross_refs(ontology)),
        ]

    print(f"\n🔍 governance validate — {ontology_path}\n")

    for name, result in checks:
        status = "✅" if result.ok else "❌"
        print(f"{status} {name}")
        for msg in result.errors:
            print(msg)
            all_errors.append(msg)
        for msg in result.warnings:
            print(msg)
            all_warnings.append(msg)

    print()
    if all_errors:
        print(f"❌ 검증 실패: {len(all_errors)}개 오류, {len(all_warnings)}개 경고\n")
        if args.strict:
            sys.exit(1)
    else:
        print(f"✅ 검증 통과 ({len(all_warnings)}개 경고)\n")


if __name__ == "__main__":
    main()
