# DEO Constraint Reasoning — Full Guide

Used in PROPOSE to generate constraint-satisfying setup paths.

## Core principles

1. **Don't select by similarity alone** — constraints take priority.
2. **Always enforce negative constraints** — "without docker", "no GPU" → remove those paths immediately.
3. **Always include reasoning** — explain why each option was chosen and why others were excluded.

## Query Decomposition

Combine user utterance with INTAKE slots into this structure:

```
positive:   what the user wants (tech stack, goal, performance)
negative:   explicit exclusions ("without X", "no X", "skip X")
hard:       must-satisfy conditions (violation → path removed immediately)
soft:       prefer-to-satisfy conditions (violation → penalty applied)
```

## Scoring

```
score(node) = sim(query_positive, node_positive)
            - sim(query_negative, node_positive)
            - sim(query_positive, node_negative)

score(path) = Σ node_scores - soft_constraint_penalty
```

Hard constraint violations remove the path entirely before scoring.

## deo_resolver.py call examples

```bash
# Natural language input
python3 skills/agent-setup-copilot/script/deo_resolver.py \
  --query "web automation server, always on, without docker" \
  --goal web_automation

# Structured input
python3 skills/agent-setup-copilot/script/deo_resolver.py \
  --json '{"positive":["web_automation","always_on"],"negative":["docker"],"constraints":{"hard":["no_docker"],"soft":["prefer_mac"]}}'

# Cloud: data isolation constraint
python3 skills/agent-setup-copilot/script/deo_resolver.py \
  --json '{"positive":["cloud_deployment","rag"],"negative":["internet_exposure"],"constraints":{"hard":["data_isolation"],"soft":["korea_region"]}}'
```

## Using the output

From deo_resolver.py's JSON:
- `decision.selected_path` → base data for Option A/B/C
- `decision.excluded_options` → explain exclusion reasons
- `decision.reasoning` → recommendation rationale summary
- `meta.query_decomposition` → verify user intent parsing
