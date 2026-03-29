#!/usr/bin/env python3
"""
DEO Resolver — Constraint-aware environment setup decision engine.

Applies Direct Embedding Optimization (DEO) principles to select optimal
setup paths from the ontology. Instead of simple similarity-based retrieval,
this module decomposes user queries into positive/negative intents and
hard/soft constraints, then scores ontology nodes and paths accordingly.

Scoring formula (per node):
  score(node) =
      sim(query_positive, node_positive)
    - sim(query_negative, node_positive)
    - sim(query_positive, node_negative)

Path scoring:
  score(path) = Σ node_scores - constraint_violation_penalty

Hard constraints prune entire paths immediately.
Soft constraints apply weighted penalties.

Usage:
  # Structured JSON input
  python3 skills/agent-setup-copilot/script/deo_resolver.py --json '{
    "positive": ["python", "fast", "lightweight"],
    "negative": ["docker", "GPU"],
    "constraints": {
      "hard": ["budget_under_1000", "no_docker"],
      "soft": ["prefer_mac"]
    }
  }'

  # Natural language input (auto-decomposed)
  python3 skills/agent-setup-copilot/script/deo_resolver.py \
    --query "fast python agent without docker and without GPU, budget under 100만원"

  # With slot context from INTAKE phase
  python3 skills/agent-setup-copilot/script/deo_resolver.py \
    --query "web automation server, always on" \
    --goal "web_automation" \
    --constraint "budget_under_1000" \
    --device "mac_mini_m4_32gb"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Constants ────────────────────────────────────────────────────────────────

HARD_PENALTY = float("inf")
SOFT_PENALTY_WEIGHT = 0.3
TOP_K = 3

# ── Data loading (reuse pattern from estimator/transition) ───────────────────

_INSTANCE_ENTITIES = [
    "use_case", "device", "model", "framework",
    "api_service", "component", "repo", "setup_profile",
    "relation",
]
_SECTION_MAP = {
    "use_case": "use_cases", "device": "devices", "model": "models",
    "framework": "frameworks", "api_service": "api_services",
    "component": "components", "repo": "repos",
    "setup_profile": "setup_profiles", "relation": "instances",
}


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_ontology() -> dict:
    onto: dict = {}
    for entity in _INSTANCE_ENTITIES:
        section = _SECTION_MAP[entity]
        fname = f"instances/{entity}.yaml"
        for base in [
            Path.home() / ".cache" / "agent-setup-copilot",
            Path(__file__).parent / "bundle",
        ]:
            path = base / fname
            if path.exists():
                data = _read_yaml(path)
                items = (
                    data.get(section)
                    or data.get(f"{entity}s")
                    or data.get(entity)
                    or []
                ) if data else []
                if items:
                    onto[section] = items
                break
    if not onto:
        raise FileNotFoundError(
            "No ontology data found. Run: "
            "python3 skills/agent-setup-copilot/script/loader.py --update"
        )
    return onto


# ── Query decomposition ─────────────────────────────────────────────────────

@dataclass
class DecomposedQuery:
    positive: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    soft_constraints: list[str] = field(default_factory=list)


# Negative signal patterns in natural language
_NEGATIVE_PATTERNS = [
    r"(?:without|no|not|제외|없이|빼고|말고)\s+(\S+)",
    r"(\S+)\s*(?:안\s*씀|안\s*쓸|쓰지\s*않|없이|빼고|말고|제외)",
]

# Hard constraint patterns
_HARD_CONSTRAINT_MAP: dict[str, list[str]] = {
    "no_docker":     ["docker", "도커", "container", "컨테이너"],
    "no_gpu":        ["gpu", "GPU", "그래픽카드", "cuda", "CUDA", "rtx", "RTX"],
    "requires_gpu":  [],  # set programmatically
    "no_fine_tuning": ["fine-tuning", "fine_tuning", "파인튜닝", "lora", "LoRA"],
    "portable_only": ["portable", "휴대", "노트북", "laptop"],
    "stationary_only": ["stationary", "고정", "서버", "server", "always-on", "상시"],
    "no_mac":        ["mac", "맥", "apple", "애플"],
    "no_pc":         ["pc", "PC", "윈도우", "windows"],
}

# Budget patterns
_BUDGET_PATTERN = re.compile(
    r"(?:budget|예산|가격)\s*(?:under|이하|미만|까지)?\s*"
    r"[$₩]?\s*([\d,.]+)\s*(만원|원|usd|USD|\$|dollars?)?"
    r"|"
    r"[$₩]\s*([\d,.]+)\s*(만원|원|usd|USD|dollars?)?"
    r"|"
    r"([\d,.]+)\s*(만원)",
    re.IGNORECASE,
)


def decompose_query(
    raw_query: str,
    slot_goal: str | None = None,
    slot_constraint: str | None = None,
    slot_device: str | None = None,
) -> DecomposedQuery:
    """Parse a natural language query into structured positive/negative/constraints."""
    q = DecomposedQuery()
    text = raw_query.lower()

    # Extract negatives
    for pattern in _NEGATIVE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            neg_term = match.group(1).strip(" ,.\t").lower()
            if neg_term:
                q.negative.append(neg_term)

    # Map negatives to hard constraints
    for constraint_id, triggers in _HARD_CONSTRAINT_MAP.items():
        for trigger in triggers:
            if trigger.lower() in [n.lower() for n in q.negative]:
                if constraint_id not in q.hard_constraints:
                    q.hard_constraints.append(constraint_id)

    # Extract budget constraint
    budget_match = _BUDGET_PATTERN.search(raw_query)
    if budget_match:
        # Find the first non-None number group across alternations
        amount_str = budget_match.group(1) or budget_match.group(3) or budget_match.group(5)
        unit_str = budget_match.group(2) or budget_match.group(4) or budget_match.group(6)
        if amount_str:
            amount = float(amount_str.replace(",", ""))
            unit = (unit_str or "").lower()
            if unit in ("만원",):
                amount_usd = int(amount * 10000 / 1300)  # approx KRW→USD
            elif unit in ("원",):
                amount_usd = int(amount / 1300)
            else:
                amount_usd = int(amount)
            q.hard_constraints.append(f"budget_under_{amount_usd}")

    # Remaining tokens are positive signals (remove negative phrases)
    clean = text
    for pattern in _NEGATIVE_PATTERNS:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
    clean = _BUDGET_PATTERN.sub("", clean)

    # Tokenize remaining positive terms
    tokens = re.findall(r"[a-z가-힣][a-z0-9가-힣._:-]*", clean)
    stop_words = {
        "and", "or", "the", "a", "an", "for", "with", "on", "in", "to",
        "i", "my", "want", "need", "설정", "환경", "세팅", "추천",
        "해주세요", "해줘", "좋겠", "싶어", "할래",
    }
    q.positive = [t for t in tokens if t not in stop_words and t not in q.negative]

    # Merge slot context
    if slot_goal:
        q.positive.insert(0, slot_goal)
    if slot_constraint:
        q.hard_constraints.append(slot_constraint)
    if slot_device:
        q.positive.append(slot_device)

    # Portability / always-on as soft constraints
    if any(k in text for k in ("portable", "휴대", "노트북", "laptop")):
        if "portable_only" not in q.hard_constraints:
            q.soft_constraints.append("prefer_portable")
    if any(k in text for k in ("always on", "상시", "서버", "server")):
        if "stationary_only" not in q.hard_constraints:
            q.soft_constraints.append("prefer_always_on")

    return q


def decompose_json(raw: str) -> DecomposedQuery:
    """Parse a JSON-formatted query decomposition."""
    obj = json.loads(raw)
    constraints = obj.get("constraints", {})
    return DecomposedQuery(
        positive=obj.get("positive", []),
        negative=obj.get("negative", []),
        hard_constraints=constraints.get("hard", []),
        soft_constraints=constraints.get("soft", []),
    )


# ── Ontology node abstraction ───────────────────────────────────────────────

@dataclass
class OntologyNode:
    """Unified representation of an ontology entity for scoring."""
    id: str
    kind: str  # device, model, framework, setup_profile, use_case
    label: str
    positive_tags: list[str] = field(default_factory=list)
    negative_tags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _extract_tags(item: dict, kind: str) -> tuple[list[str], list[str]]:
    """Extract positive and negative tags from an ontology item."""
    pos: list[str] = []
    neg: list[str] = []

    item_id = item.get("id", "")
    pos.append(item_id.lower())

    label = item.get("label", "")
    pos.extend(re.findall(r"[a-z가-힣][a-z0-9가-힣._:-]*", label.lower()))

    if kind == "device":
        pos.append(item.get("type", ""))
        pos.append(item.get("tier", ""))
        if item.get("portability"):
            pos.append(item["portability"])
        if item.get("always_on"):
            pos.append("always_on")
        if item.get("chip"):
            pos.append(item["chip"].lower())
        # Supported use cases
        supported = item.get("supported_use_cases", [])
        if isinstance(supported, list):
            pos.extend(supported)
        elif supported == "all":
            pos.append("all_use_cases")
        # Negative: unsupported use cases
        unsupported = item.get("unsupported_use_cases", [])
        if isinstance(unsupported, list):
            neg.extend(unsupported)
        # GPU presence
        if item.get("gpu_vram_gb", 0) > 0:
            pos.append("gpu")
            pos.append("cuda")
        else:
            neg.append("gpu_native")

    elif kind == "model":
        pos.append(item.get("type", "").lower())  # dense, MoE, reasoning
        pos.append(item.get("quality", ""))
        if item.get("tool_calling"):
            pos.append("tool_calling")
        else:
            neg.append("tool_calling")
        if item.get("sweet_spot"):
            pos.append("sweet_spot")

    elif kind == "framework":
        pos.append(item.get("kind", ""))  # agent, automation, ui, ide, rag
        pos.append(item.get("complexity", ""))
        if item.get("multiagent"):
            pos.append("multiagent")
        if item.get("mcp_support"):
            pos.append("mcp")
        best_for = item.get("best_for", [])
        if isinstance(best_for, list):
            pos.extend(best_for)
        runtimes = item.get("runtime_support", [])
        if isinstance(runtimes, list):
            pos.extend(runtimes)
        # Docker-dependent frameworks
        install = str(item.get("install", ""))
        if "docker" in install.lower():
            pos.append("docker")
            neg.append("no_docker")

    elif kind == "setup_profile":
        pos.extend(item.get("devices", []))
        pos.append(item.get("model", ""))
        pos.append(item.get("framework", ""))
        use_cases = item.get("use_cases", [])
        if isinstance(use_cases, list):
            pos.extend(use_cases)
        elif use_cases == "all":
            pos.append("all_use_cases")
        pos.append(item.get("complexity", ""))
        if item.get("always_on"):
            pos.append("always_on")
        # Check if any setup step uses docker
        steps = item.get("setup_steps", [])
        if any("docker" in str(s).lower() for s in steps):
            pos.append("docker")
            neg.append("no_docker")

    elif kind == "use_case":
        keywords = item.get("keywords", [])
        pos.extend([k.lower() for k in keywords])
        if item.get("requires_gpu"):
            pos.append("requires_gpu")
            neg.append("no_gpu")
        if item.get("needs_always_on"):
            pos.append("always_on")

    # Clean
    pos = [t.lower().strip() for t in pos if t]
    neg = [t.lower().strip() for t in neg if t]
    return pos, neg


def build_nodes(ontology: dict) -> list[OntologyNode]:
    """Build OntologyNode list from all ontology entities."""
    nodes: list[OntologyNode] = []
    entity_map = {
        "devices": "device",
        "models": "model",
        "frameworks": "framework",
        "setup_profiles": "setup_profile",
        "use_cases": "use_case",
    }
    for section, kind in entity_map.items():
        for item in ontology.get(section, []):
            pos, neg = _extract_tags(item, kind)
            nodes.append(OntologyNode(
                id=item.get("id", ""),
                kind=kind,
                label=item.get("label", ""),
                positive_tags=pos,
                negative_tags=neg,
                raw=item,
            ))
    return nodes


# ── Scoring ──────────────────────────────────────────────────────────────────

def _tag_overlap(query_terms: list[str], node_tags: list[str]) -> float:
    """Jaccard-like overlap score between query terms and node tags."""
    if not query_terms or not node_tags:
        return 0.0
    q_set = set(query_terms)
    n_set = set(node_tags)
    intersection = q_set & n_set
    if not intersection:
        # Substring matching fallback
        count = 0
        for qt in q_set:
            for nt in n_set:
                if qt in nt or nt in qt:
                    count += 1
                    break
        return count / max(len(q_set), 1)
    return len(intersection) / max(len(q_set), 1)


def score_node(query: DecomposedQuery, node: OntologyNode) -> float:
    """
    DEO scoring formula:
      score = sim(q+, n+) - sim(q-, n+) - sim(q+, n-)
    """
    pos_pos = _tag_overlap(query.positive, node.positive_tags)
    neg_pos = _tag_overlap(query.negative, node.positive_tags)
    pos_neg = _tag_overlap(query.positive, node.negative_tags)
    return pos_pos - neg_pos - pos_neg


# ── Constraint enforcement ───────────────────────────────────────────────────

def _parse_budget_constraint(constraint: str) -> int | None:
    """Extract USD budget limit from constraint string like 'budget_under_800'."""
    m = re.match(r"budget_under_(\d+)", constraint)
    return int(m.group(1)) if m else None


def _device_price_usd(device: dict) -> int | None:
    """Extract approximate USD price from device data."""
    if "price_usd" in device:
        return int(device["price_usd"])
    price_range = device.get("price_range", "")
    # Parse Korean won format: "120만원~"
    m = re.search(r"([\d,.]+)\s*만원", price_range)
    if m:
        return int(float(m.group(1)) * 10000 / 1300)
    # Parse USD format: "~$3,000"
    m = re.search(r"\$\s*([\d,]+)", price_range)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def check_hard_constraints(
    query: DecomposedQuery, node: OntologyNode
) -> list[str]:
    """Return list of violated hard constraints. Empty = passes."""
    violations: list[str] = []

    for hc in query.hard_constraints:
        # Docker constraint
        if hc == "no_docker":
            if "docker" in node.positive_tags:
                violations.append(f"hard: {hc} — node uses docker")

        # GPU constraint
        elif hc == "no_gpu":
            if node.kind == "device" and node.raw.get("gpu_vram_gb", 0) > 0:
                violations.append(f"hard: {hc} — device has dedicated GPU")
            if node.kind == "use_case" and node.raw.get("requires_gpu"):
                violations.append(f"hard: {hc} — use case requires GPU")

        # Portability
        elif hc == "portable_only":
            if node.kind == "device" and node.raw.get("portability") != "portable":
                violations.append(f"hard: {hc} — device is not portable")

        elif hc == "stationary_only":
            if node.kind == "device" and node.raw.get("portability") != "stationary":
                violations.append(f"hard: {hc} — device is not stationary")

        # Platform exclusions
        elif hc == "no_mac":
            if node.kind == "device" and node.raw.get("type", "").startswith("mac"):
                violations.append(f"hard: {hc} — Mac device excluded")

        elif hc == "no_pc":
            if node.kind == "device" and node.raw.get("type") == "pc":
                violations.append(f"hard: {hc} — PC excluded")

        # Budget
        elif hc.startswith("budget_under_"):
            budget = _parse_budget_constraint(hc)
            if budget and node.kind == "device":
                price = _device_price_usd(node.raw)
                if price and price > budget:
                    violations.append(
                        f"hard: {hc} — device ~${price} exceeds ${budget}"
                    )

    return violations


def check_soft_constraints(
    query: DecomposedQuery, node: OntologyNode
) -> float:
    """Return total penalty from soft constraint violations."""
    penalty = 0.0

    for sc in query.soft_constraints:
        if sc == "prefer_portable":
            if node.kind == "device" and node.raw.get("portability") != "portable":
                penalty += SOFT_PENALTY_WEIGHT

        elif sc == "prefer_always_on":
            if node.kind == "device" and not node.raw.get("always_on"):
                penalty += SOFT_PENALTY_WEIGHT

        elif sc == "prefer_mac":
            if node.kind == "device" and not node.raw.get("type", "").startswith("mac"):
                penalty += SOFT_PENALTY_WEIGHT

        elif sc == "prefer_low_complexity":
            complexity = node.raw.get("complexity", "low")
            if complexity == "high":
                penalty += SOFT_PENALTY_WEIGHT
            elif complexity == "medium":
                penalty += SOFT_PENALTY_WEIGHT * 0.5

    return penalty


# ── Path construction & scoring ──────────────────────────────────────────────

@dataclass
class SetupPath:
    """A candidate setup path: device + model + framework (+ optional profile)."""
    device: OntologyNode | None = None
    model: OntologyNode | None = None
    framework: OntologyNode | None = None
    use_case: OntologyNode | None = None
    profile: OntologyNode | None = None
    score: float = 0.0
    hard_violations: list[str] = field(default_factory=list)
    soft_penalty: float = 0.0

    @property
    def components(self) -> list[OntologyNode]:
        return [n for n in [self.device, self.model, self.framework,
                            self.use_case, self.profile] if n]

    @property
    def net_score(self) -> float:
        return self.score - self.soft_penalty

    @property
    def is_valid(self) -> bool:
        return len(self.hard_violations) == 0


def _memory_compatible(device: dict, model: dict) -> bool:
    """Check if a model fits on a device."""
    dev_mem = device.get("memory_gb", 0)
    if device.get("type") == "pc" and device.get("gpu_vram_gb", 0) > 0:
        dev_mem = device["gpu_vram_gb"]
    model_min = model.get("min_memory_gb", 0)
    return dev_mem >= model_min


def _framework_supports_use_case(framework: dict, use_case_id: str) -> bool:
    best_for = framework.get("best_for", [])
    return use_case_id in best_for


def build_paths_from_profiles(
    query: DecomposedQuery, nodes: list[OntologyNode], ontology: dict
) -> list[SetupPath]:
    """Build paths from curated setup_profiles."""
    paths: list[SetupPath] = []
    profiles = [n for n in nodes if n.kind == "setup_profile"]
    devices_by_id = {n.id: n for n in nodes if n.kind == "device"}
    models_by_id = {n.id: n for n in nodes if n.kind == "model"}
    frameworks_by_id = {n.id: n for n in nodes if n.kind == "framework"}

    for prof in profiles:
        path = SetupPath(profile=prof)

        # Link components
        dev_ids = prof.raw.get("devices", [])
        if dev_ids:
            path.device = devices_by_id.get(dev_ids[0])
        model_id = prof.raw.get("model", "")
        path.model = models_by_id.get(model_id)
        fw_id = prof.raw.get("framework", "")
        path.framework = frameworks_by_id.get(fw_id)

        # Score all components
        total_score = 0.0
        all_violations: list[str] = []
        total_penalty = 0.0

        for component in path.components:
            total_score += score_node(query, component)
            all_violations.extend(check_hard_constraints(query, component))
            total_penalty += check_soft_constraints(query, component)

        path.score = total_score
        path.hard_violations = all_violations
        path.soft_penalty = total_penalty
        paths.append(path)

    return paths


def build_paths_combinatorial(
    query: DecomposedQuery, nodes: list[OntologyNode], ontology: dict
) -> list[SetupPath]:
    """Build paths by combining top-scoring devices × models × frameworks."""
    devices = [n for n in nodes if n.kind == "device"]
    models = [n for n in nodes if n.kind == "model"]
    frameworks = [n for n in nodes if n.kind == "framework"]

    # Pre-score and filter to top candidates per category
    def top_n(node_list: list[OntologyNode], n: int = 5) -> list[OntologyNode]:
        scored = []
        for node in node_list:
            violations = check_hard_constraints(query, node)
            if not violations:
                s = score_node(query, node)
                scored.append((s, node))
        scored.sort(key=lambda x: -x[0])
        return [node for _, node in scored[:n]]

    top_devices = top_n(devices, 5)
    top_models = top_n(models, 5)
    top_frameworks = top_n(frameworks, 5)

    paths: list[SetupPath] = []
    for dev in top_devices:
        for mod in top_models:
            # Memory compatibility check
            if not _memory_compatible(dev.raw, mod.raw):
                continue
            for fw in top_frameworks:
                path = SetupPath(device=dev, model=mod, framework=fw)
                total_score = (
                    score_node(query, dev)
                    + score_node(query, mod)
                    + score_node(query, fw)
                )
                all_violations: list[str] = []
                total_penalty = 0.0
                for component in path.components:
                    all_violations.extend(check_hard_constraints(query, component))
                    total_penalty += check_soft_constraints(query, component)

                path.score = total_score
                path.hard_violations = all_violations
                path.soft_penalty = total_penalty
                paths.append(path)

    return paths


# ── Main resolver ────────────────────────────────────────────────────────────

@dataclass
class Resolution:
    selected_paths: list[SetupPath]
    excluded_paths: list[SetupPath]
    query: DecomposedQuery
    all_paths_count: int


def resolve(query: DecomposedQuery, ontology: dict, top_k: int = TOP_K) -> Resolution:
    """Run the full DEO resolution pipeline."""
    nodes = build_nodes(ontology)

    # Build candidate paths from both profiles and combinatorial
    profile_paths = build_paths_from_profiles(query, nodes, ontology)
    combo_paths = build_paths_combinatorial(query, nodes, ontology)
    all_paths = profile_paths + combo_paths

    # Partition into valid and excluded
    valid = [p for p in all_paths if p.is_valid]
    excluded = [p for p in all_paths if not p.is_valid]

    # Sort valid paths by net score (descending)
    valid.sort(key=lambda p: -p.net_score)

    # Deduplicate: avoid recommending same device+model twice
    seen: set[str] = set()
    deduped: list[SetupPath] = []
    for p in valid:
        key = (
            (p.device.id if p.device else "")
            + "|" + (p.model.id if p.model else "")
            + "|" + (p.framework.id if p.framework else "")
        )
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    selected = deduped[:top_k]

    return Resolution(
        selected_paths=selected,
        excluded_paths=excluded[:10],  # keep top excluded for reasoning
        query=query,
        all_paths_count=len(all_paths),
    )


# ── Output formatting ────────────────────────────────────────────────────────

def _path_summary(path: SetupPath) -> dict:
    summary: dict[str, Any] = {}
    if path.profile:
        summary["profile"] = path.profile.id
        summary["profile_label"] = path.profile.label
    if path.device:
        summary["device"] = path.device.id
        summary["device_label"] = path.device.label
    if path.model:
        summary["model"] = path.model.id
    if path.framework:
        summary["framework"] = path.framework.id
        summary["framework_label"] = path.framework.label
    summary["score"] = round(path.net_score, 3)
    return summary


def format_output(resolution: Resolution) -> dict:
    """Format the resolution as the DEO output schema."""
    selected = []
    for p in resolution.selected_paths:
        entry = _path_summary(p)
        entry["reasoning"] = []
        for comp in p.components:
            overlap = set(resolution.query.positive) & set(comp.positive_tags)
            if overlap:
                entry["reasoning"].append(
                    f"{comp.kind}:{comp.id} matches [{', '.join(sorted(overlap))}]"
                )
        selected.append(entry)

    excluded = []
    for p in resolution.excluded_paths[:5]:
        entry = _path_summary(p)
        entry["violations"] = p.hard_violations[:3]
        excluded.append(entry)

    # Reasoning trace
    reasoning_parts = []
    if selected:
        reasoning_parts.append(
            "Selected: "
            + "; ".join(
                f"{s.get('device', '?')}+{s.get('model', '?')}+{s.get('framework', '?')}"
                for s in selected
            )
        )
    if resolution.query.negative:
        reasoning_parts.append(
            f"Excluded signals: {', '.join(resolution.query.negative)}"
        )
    if resolution.query.hard_constraints:
        reasoning_parts.append(
            f"Hard constraints enforced: {', '.join(resolution.query.hard_constraints)}"
        )
    if resolution.query.soft_constraints:
        reasoning_parts.append(
            f"Soft constraints applied: {', '.join(resolution.query.soft_constraints)}"
        )

    return {
        "decision": {
            "selected_path": selected,
            "excluded_options": excluded,
            "constraint_analysis": {
                "hard_constraints": resolution.query.hard_constraints,
                "soft_constraints": resolution.query.soft_constraints,
                "violations": [
                    v for p in resolution.excluded_paths[:5]
                    for v in p.hard_violations[:2]
                ],
            },
            "reasoning": " | ".join(reasoning_parts),
        },
        "meta": {
            "total_paths_evaluated": resolution.all_paths_count,
            "valid_paths": len(resolution.selected_paths),
            "pruned_paths": len(resolution.excluded_paths),
            "query_decomposition": {
                "positive": resolution.query.positive,
                "negative": resolution.query.negative,
                "hard_constraints": resolution.query.hard_constraints,
                "soft_constraints": resolution.query.soft_constraints,
            },
        },
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="DEO Resolver — constraint-aware environment setup decision engine"
    )
    p.add_argument("--query", help="Natural language query")
    p.add_argument("--json", dest="json_input",
                   help="Structured JSON query (positive/negative/constraints)")
    p.add_argument("--goal", help="Slot: user goal (use_case id)")
    p.add_argument("--constraint", help="Slot: hard constraint")
    p.add_argument("--device", help="Slot: target device id")
    p.add_argument("--top-k", type=int, default=TOP_K,
                   help="Number of top paths to return (default: 3)")
    args = p.parse_args()

    if not args.query and not args.json_input:
        p.error("Provide --query or --json")

    # Decompose query
    if args.json_input:
        query = decompose_json(args.json_input)
    else:
        query = decompose_query(
            args.query,
            slot_goal=args.goal,
            slot_constraint=args.constraint,
            slot_device=args.device,
        )

    # Load ontology
    try:
        ontology = load_ontology()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Resolve
    resolution = resolve(query, ontology, top_k=args.top_k)

    # Output
    output = format_output(resolution)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
