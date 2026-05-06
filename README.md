# agent-setup-copilot

**Local AI Agent Setup Advisor — Claude Code Skill**

Ask in your terminal: "What should I buy to run OpenClaw?" or "When should I switch from the API to local?"

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> Ontology data (devices, models, frameworks, repos, setup profiles, cost info) is maintained in
> **[agent-setup-ontology](https://github.com/WMJOON/agent-setup-ontology)**.

---

## What it does

Recommends the right local AI agent stack based on your goal, budget, and current usage.

- **Device recommendation** — given your use case, which Mac or PC build to buy
- **Model + framework pairing** — which Ollama model and framework fit your needs
- **Repo setup guide** — install commands and quickstart code for each framework
- **Setup profiles** — curated end-to-end configurations (single or multi-device)
- **Cost analysis** — estimated API spend vs local hardware break-even
- **Transition timing** — when to switch from cloud API to local setup based on usage growth
- **Performance estimates** — tokens/sec for any device x model combination
- **Simple capability summaries** — "What can this machine realistically do?" in plain language

Powered by Claude Code. No Ollama or API key needed to run the advisor itself.

---

## Install

```bash
git clone https://github.com/WMJOON/agent-setup-copilot \
  ~/.claude/skills/agent-setup-copilot
```

That's it. Ask Claude Code directly:

```
"I have a Mac Mini M4 32GB — what agent stack should I use?"
"I spend $20/month on Claude Haiku. When should I go local?"
"How fast is qwen3.5:35b-a3b on my device?"
"How do I set up OpenClaw?"
"Compare AutoGen vs CrewAI for multi-agent pipelines"
"Mac mini M4 32GB인데 쉽게 설명해줘"
"What can my machine realistically handle?"
```

---

## Scripts (used by the skill)

| Script | Purpose |
|--------|---------|
| `script/loader.py` | Fetch concepts + instances from SOT |
| `script/estimator.py` | Estimate tokens/second for device x model |
| `script/transition.py` | Calculate optimal API → local transition month |
| `script/deo_resolver.py` | DEO constraint-aware setup path resolver |
| `script/sync_ontology_bundle.py` | Sync ontology SoT into copilot bundle + cache |
| `script/surface_advisor.py` | Rank CLI / IDE / API surfaces by fit and headless suitability |
| `script/knowledge_advisor.py` | Term/path explanations at simple / technical / dual level |

```bash
SCRIPT=skills/agent-setup-copilot/script

python3 $SCRIPT/loader.py --update
python3 $SCRIPT/estimator.py --device mac_mini_m4_32gb --compare-models
python3 $SCRIPT/estimator.py --device mac_mini_m4_32gb --summary-style simple
python3 $SCRIPT/transition.py --api claude-haiku-4-5 --monthly-cost 15 --growth 10
python3 $SCRIPT/deo_resolver.py --query "fast agent without docker" --goal web_automation
python3 $SCRIPT/sync_ontology_bundle.py --smoke-test
```

---

## Eval (Phase G — output quality)

추천 품질과 데이터 신선도를 평가하는 Eval 레이어.

| Script | What it checks |
|--------|---------------|
| `script/eval/freshness_eval.py` | 온톨로지 데이터 신선도 (`updated_at` / `last_verified` 기준) |
| `script/eval/estimator_eval.py` | estimator 예측 t/s vs `speed_note` 실측 범위 비교 |
| `script/eval/recommendation_eval.py` | golden cases 기반 추천 품질 (프로그래매틱 + LLM-as-judge) |
| `script/eval/golden_cases.yaml` | 전문가 정의 ground truth 케이스 |

```bash
EVAL=skills/agent-setup-copilot/script/eval
INSTANCES=../agent-setup-ontology/instances  # 또는 로컬 경로

# 온톨로지 신선도
python3 $EVAL/freshness_eval.py --instances-dir $INSTANCES

# estimator 정확도 (speed_note 대비)
python3 $EVAL/estimator_eval.py --instances-dir $INSTANCES

# 추천 품질 (golden cases 5개)
python3 $EVAL/recommendation_eval.py --instances-dir $INSTANCES

# LLM-as-judge 포함 (ANTHROPIC_API_KEY 필요)
python3 $EVAL/recommendation_eval.py --instances-dir $INSTANCES --llm-judge
```

### Example: plain-language device summary

```bash
python3 skills/agent-setup-copilot/script/estimator.py \
  --device mac_mini_m4_32gb \
  --summary-style simple
```

Example output shape:

```text
=== 쉬운 요약 — Mac Mini M4 32GB ===

한 줄 결론
- 개인용 로컬 AI/자동화 서버로 충분히 실용적입니다.

잘하는 것
- 웹 자동화
- 코드 생성·보조
- 일반 Q&A 챗봇

애매한 것
- 딥리서치 (느리지만 가능)

비추천
- 파인튜닝 (장비 정책상 비권장)
```

---

## Governance

The schema contract (required fields, types, enums) that
[agent-setup-ontology](https://github.com/WMJOON/agent-setup-ontology) must conform to
lives in [`governance/`](governance/).

```bash
# Validate ontology against contract (single file)
python governance/scripts/validate.py --ontology path/to/ontology.yaml --strict

# Validate per-entity instance directory
python governance/scripts/validate.py --instances-dir path/to/instances/ --strict
```

---

## Contributing to the ontology

To add devices, models, frameworks, or repos, open a PR on
**[agent-setup-ontology](https://github.com/WMJOON/agent-setup-ontology)**.
No code knowledge required — just edit the relevant file in `instances/`.

---

## License

MIT
