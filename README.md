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
```

---

## Scripts (used by the skill)

| Script | Purpose |
|--------|---------|
| `skills/agent-setup-copilot/script/loader.py` | Fetch concepts + instances from SOT |
| `skills/agent-setup-copilot/script/estimator.py` | Estimate tokens/second for device x model |
| `skills/agent-setup-copilot/script/transition.py` | Calculate optimal API -> local transition month |
| `skills/agent-setup-copilot/script/deo_resolver.py` | DEO constraint-aware setup path resolver |

```bash
# Examples (run directly or via Claude Code)
python3 skills/agent-setup-copilot/script/loader.py --update
python3 skills/agent-setup-copilot/script/estimator.py --device mac_mini_m4_32gb --compare-models
python3 skills/agent-setup-copilot/script/transition.py --api claude-haiku-4-5 --monthly-cost 15 --growth 10
python3 skills/agent-setup-copilot/script/deo_resolver.py --query "fast agent without docker" --goal web_automation
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
