# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_estimator_policy.py

# Run a single test by name
pytest tests/test_estimator_policy.py::test_summary_model_uses_device_max_model

# Refresh ontology cache from GitHub
python3 skills/agent-setup-copilot/script/loader.py --update

# Sync specific bundle files (api_service, relation) from ontology SOT
python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py --smoke-test

# Validate ontology instance files against governance schema
python governance/scripts/validate.py --instances-dir path/to/instances/ --strict

# Estimator CLI examples
python3 skills/agent-setup-copilot/script/estimator.py --device mac_mini_m4_32gb --model qwen3.5:35b-a3b
python3 skills/agent-setup-copilot/script/estimator.py --device mac_mini_m4_32gb --compare-models
python3 skills/agent-setup-copilot/script/estimator.py --device mac_mini_m4_32gb --summary-style simple

# Eval layer
python3 skills/agent-setup-copilot/script/eval/freshness_eval.py
python3 skills/agent-setup-copilot/script/eval/estimator_eval.py
python3 skills/agent-setup-copilot/script/eval/recommendation_eval.py --llm-judge
```

## Architecture

This repo has two distinct layers:

### 1. Claude Code Skill (`skills/agent-setup-copilot/`)

The skill itself is `SKILL.md` — Claude Code reads this file and runs as a conversational advisor following a **5-state machine**: DETECT → INTAKE → GATE → PROPOSE → DONE. The Python scripts in `script/` are tools Claude invokes during the PROPOSE state only. Claude is the LLM; no external model is needed to run the skill.

Key constraint: scripts are never called before GATE. All state is held in Claude's context — no file writes.

### 2. Governance (`governance/`)

This repo *owns the schema contract* that the separate `agent-setup-ontology` repo must conform to. `governance/schema.json` is the Source of Truth; `governance/scripts/validate.py` is the canonical validator used by both repos' CI.

### Data flow

```
agent-setup-ontology (GitHub) ──fetch──► ~/.cache/agent-setup-copilot/
                                                    │
                              script/bundle/ ◄──────┘ (fallback if cache empty)
                                    │
                              loader.py / estimator.py / deo_resolver.py / ...
```

`loader.py` fetches from GitHub (or cache, or bundle fallback) and prints YAML to stdout for Claude to read. Cache TTL is 24 hours. The `AGENT_COPILOT_BASE_URL` env var overrides the GitHub raw URL for local development.

### Script responsibilities

| Script | Role |
|---|---|
| `loader.py` | Fetch all ontology concepts + instances; print to stdout |
| `estimator.py` | t/s estimation + use-case suitability; imports as module in tests |
| `deo_resolver.py` | DEO constraint reasoning — positive/negative/hard/soft constraints → top-3 paths |
| `transition.py` | API → local break-even and optimal switch month |
| `surface_advisor.py` | Rank CLI/IDE/API surfaces by fit and headless suitability |
| `knowledge_advisor.py` | Term/path explanations at simple/technical/dual level |
| `sync_ontology_bundle.py` | Sync `api_service` + `relation` bundle files from ontology SOT |

### Ontology entities

Ontology data lives in `agent-setup-ontology` (separate repo) and is referenced here only via bundle snapshots (`script/bundle/`) and cache. Entities: `device`, `model`, `framework`, `use_case`, `component`, `repo`, `setup_profile`, `api_service`, `cost_estimation`, `relation`, `semantic_labels`. The `relation.yaml` instance file contains cross-entity join tables (framework↔use_case, model↔use_case, profile↔use_case).

### Tests

Tests import `estimator.py` directly as a module via `conftest.load_estimator_module()` (no package install needed). `test_skill_contract.py` asserts invariants on `SKILL.md` text. `test_ontology_alignment.py` asserts cross-entity referential integrity (e.g., `max_model` IDs exist).

When adding a new device or model to the bundle, run `test_ontology_alignment.py` and `test_estimator_policy.py` to catch broken references and policy violations before committing.
