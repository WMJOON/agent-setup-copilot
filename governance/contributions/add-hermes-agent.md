# Instruction: Add Hermes Agent to the Ontology

**Target repo:** [`agent-setup-ontology`](https://github.com/WMJOON/agent-setup-ontology)
**Goal:** Promote `hermes-agent` from a relation-only reference to a fully defined
framework with concrete repo and setup-profile entries, so that
`deo_resolver.py`, `loader.py`, and `estimator.py` can return Hermes-based
recommendations.

> **Status check (as of this instruction):**
> `hermes-agent` already appears in `instances/relation.yaml` under
> `framework_use_case_fits` and is referenced by two profile IDs
> (`setup-mac-mini-hermes-agent`, `setup-cpu-host-hermes-agent-hosted-model`).
> The framework, repo, and the two profiles are **NOT yet defined** in
> `instances/framework.yaml`, `instances/repo.yaml`, or
> `instances/setup_profile.yaml`. This instruction closes that gap.

---

## 0. Prerequisites

- Clone both repos side-by-side:
  ```bash
  git clone https://github.com/WMJOON/agent-setup-copilot
  git clone https://github.com/WMJOON/agent-setup-ontology
  ```
- Verify upstream Hermes Agent facts before merging:
  - GitHub repo URL (used in `repo.github` and `repo.install`)
  - Install command (npm / pip / docker)
  - Approximate GitHub stars (`stars_approx`)
  - Whether it speaks Ollama natively (`ollama_compatible`, `runtime_support`)
  - Minimum recommended memory for the local profile (`min_memory_gb`)

  Treat any field below marked `# TBD` as a value that must be **verified
  against Hermes' official README** before opening the PR. Do not invent URLs
  or commands.

---

## 1. Files to modify in `agent-setup-ontology`

| File | Change |
|---|---|
| `instances/framework.yaml` | **Add** one entry under `instances:` with `id: hermes-agent` |
| `instances/repo.yaml` | **Add** one entry with `id: repo-hermes-agent` |
| `instances/setup_profile.yaml` | **Add** two profiles: `setup-mac-mini-hermes-agent`, `setup-cpu-host-hermes-agent-hosted-model` |
| `instances/relation.yaml` | **No change** — the references already exist |

The schema contract these entries must satisfy lives in
[`agent-setup-copilot/governance/schema.json`](../schema.json) — see the
`frameworks`, `repos`, and `setup_profiles` sections.

---

## 2. Entries to add

### 2.1 `instances/framework.yaml`

Append under the existing `instances:` list, in the agent block (before the UI
front-ends section, alongside `openclaw`):

```yaml
  - id: hermes-agent
    label: "Hermes Agent"
    kind: agent
    complexity: medium
    local_capable: true
    runtime_support: [ollama, openai, anthropic]   # verify against Hermes docs
    multiagent: false
    mcp_support: false   # set true only if Hermes ships an MCP adapter
    install: "https://github.com/<owner>/hermes-agent"   # TBD: replace with canonical install URL
    best_for: [personal_assistant, schedule_task, file_automation, web_automation, email_assistant, home_dashboard_agent, browser_operator]
    note: >
      Personal assistant with persistent memory + learned skills.
      40+ tools (shell, file, browser, email). Built-in cron scheduling.
      Local / Docker / SSH execution backends. Serverless backends via
      Modal / Daytona / Vercel for always-on without dedicated hardware.
      Messenger integrations: Telegram, Discord, Slack, WhatsApp, Signal.
```

**Schema rules to keep in mind** (from `schema.json` →
`properties.frameworks.items`):

- `kind` must be one of `agent | automation | ui | ide | rag` → use **`agent`**.
- `complexity` must be one of `low | medium | high`.
- `runtime_support` items must come from
  `ollama | openai | anthropic | huggingface | litellm | any`.
- `best_for` items should reference existing `use_case.id`s
  (verify against `instances/use_case.yaml`).
- `additionalProperties: false` — do not add fields outside the schema.

### 2.2 `instances/repo.yaml`

Append under the agent section, alongside `repo-openclaw`:

```yaml
  - id: repo-hermes-agent
    label: "Hermes Agent"
    github: "<owner>/hermes-agent"   # TBD: verify
    framework_ref: hermes-agent
    category: agent
    stars_approx: "TBD"              # TBD: e.g. "5K+"
    min_model_quality: standard      # light | standard | standard-plus | pro
    min_memory_gb: 16                # TBD: confirm with Hermes docs
    ollama_compatible: true          # TBD: verify
    install: |
      git clone https://github.com/<owner>/hermes-agent
      cd hermes-agent && npm install     # TBD: verify (pip / npm / docker)
      cp .env.example .env               # set OLLAMA_HOST or hosted API keys
      npm start
    setup_guide: ""                  # optional: link to a community setup guide
    awesome_list: ""                 # optional
    note: >
      Personal assistant agent. Persistent memory + learned skills.
      Telegram / Discord / Slack / WhatsApp / Signal channels.
      Cron scheduling built-in; serverless deploy via Modal / Daytona / Vercel.
```

**Schema rules:**

- `category` must mirror the framework `kind` and be one of
  `agent | automation | ui | ide | rag` → **`agent`**.
- `framework_ref` must equal the framework `id` (`hermes-agent`).
- `min_model_quality` must come from `light | standard | standard-plus | pro`.

### 2.3 `instances/setup_profile.yaml`

Append the two profiles already referenced by `relation.yaml`. Place them near
the existing Mac Mini profiles for readability.

#### A. Always-on local — Mac Mini M4 32GB

```yaml
  - id: setup-mac-mini-hermes-agent
    label: "Personal Assistant Server: Mac Mini M4 32GB + Hermes Agent"
    devices: [mac_mini_m4_32gb]
    model: "qwen3.5:35b-a3b"
    framework: hermes-agent
    repo: repo-hermes-agent
    use_cases: [personal_assistant, schedule_task, file_automation, home_dashboard_agent, email_assistant]
    complexity: medium
    always_on: true
    monthly_cost: "$0 (local only)"
    note: >
      Always-on private assistant. Hermes' built-in cron + persistent memory
      run natively on the Mac Mini without an extra scheduler. 35b-a3b MoE
      keeps latency acceptable for messaging workflows over Telegram / Slack.
```

#### B. CPU-only host + hosted frontier model

```yaml
  - id: setup-cpu-host-hermes-agent-hosted-model
    label: "Hosted Assistant: CPU Host + Hermes Agent + Hosted Model"
    devices: [pc_no_gpu]
    model: "claude-haiku-4-5"            # or any hosted frontier model id
    framework: hermes-agent
    repo: repo-hermes-agent
    use_cases: [personal_assistant, schedule_task, email_assistant]
    complexity: low
    always_on: false
    monthly_cost: "~$10–30 (hosted API + serverless)"
    note: >
      Cheapest path to a Hermes assistant when no local GPU is available.
      Host runs only the agent loop; inference is offloaded to a hosted API.
      Schedule via Hermes' Modal / Daytona / Vercel serverless backends so a
      permanent always-on box is not required.
```

**Schema rules to keep in mind** (from
`properties.setup_profiles.items`):

- `devices` must be a non-empty array of existing `device.id` strings.
- `framework` must equal an existing `framework.id`.
- `repo` must equal an existing `repo.id`.
- `use_cases` items must each be an existing `use_case.id`, OR the literal
  string `"all"` (mutually exclusive with the array form).
- `complexity` must be `low | medium | high`.
- `additionalProperties: false`.

---

## 3. Validate

Run from the `agent-setup-copilot` checkout:

```bash
# 1) Schema validation (per-entity instances directory)
python governance/scripts/validate.py \
  --instances-dir ../agent-setup-ontology/instances/ \
  --strict

# 2) Smoke-test the bundle pipeline
python skills/agent-setup-copilot/script/sync_ontology_bundle.py --smoke-test

# 3) Confirm Hermes now surfaces in the resolver
python skills/agent-setup-copilot/script/deo_resolver.py \
  --query "personal assistant with cron and messaging" \
  --goal personal_assistant
```

Expected outcomes:

- `validate.py` exits 0 with no errors.
- `deo_resolver.py` returns at least one path with `framework: hermes-agent`
  and one of the new profile IDs in `selected_path`.

If validation fails, fix the offending field — **do not** loosen the schema.
Schema changes require a separate PR against `agent-setup-copilot/governance/`.

---

## 4. Commit & PR

In `agent-setup-ontology`:

```bash
git checkout -b add-hermes-agent
git add instances/framework.yaml instances/repo.yaml instances/setup_profile.yaml
git commit -m "Add hermes-agent framework, repo, and two setup profiles

Closes the gap where relation.yaml already references hermes-agent
and two profile IDs that had no concrete definitions.

- framework.yaml: add hermes-agent (kind: agent)
- repo.yaml: add repo-hermes-agent linked to the framework
- setup_profile.yaml: add setup-mac-mini-hermes-agent and
  setup-cpu-host-hermes-agent-hosted-model"
git push -u origin add-hermes-agent
```

Open the PR with this checklist in the description:

- [ ] Verified Hermes' official GitHub URL and install command
- [ ] Filled in `stars_approx`, `min_memory_gb`, `ollama_compatible`
- [ ] `runtime_support` reflects what Hermes actually supports
- [ ] `validate.py --strict` passes
- [ ] `deo_resolver.py` surfaces `hermes-agent` for a relevant query
- [ ] No `relation.yaml` edits (existing references remain valid)

---

## 5. Out of scope (do NOT do here)

- Editing `instances/relation.yaml` — Hermes is already wired in there.
- Editing `governance/schema.json` — schema is owned by `agent-setup-copilot`.
- Adding Hermes to the `bundle/` cache in `agent-setup-copilot` by hand —
  that cache is regenerated by `sync_ontology_bundle.py` after the SoT PR
  merges.
