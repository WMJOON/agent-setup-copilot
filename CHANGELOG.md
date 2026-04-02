# Changelog
All notable changes to this project will be documented in this file.

## [0.0.8] - 2026-04-02
### Fixed
- `SKILL.md`: added Tone section with explicit anti-patterns (no activation announcements, no formal honorifics, no user-type labels spoken aloud, 1 question per turn). Added bad/good example for target conversational register.
- `SKILL.md`: translated Categorical Semantic Tracing Rule example from Korean to English.

## [0.0.7] - 2026-04-02
### Added
- `script/bundle/concepts/semantic_labels.yaml`: bundle copy of Semantic Label entities (always_on_friendly, portable_ready, cost_effective, team_scale_bottleneck, maintenance_free, high_security_compliance) with derivation rules.
- `script/knowledge_advisor.py`: CLI tool for terminology lookup against the ontology bundle; supports --level simple/technical/dual.
- `user_scale` slot (6th slot) to INTAKE: captures single/team/enterprise scale for Semantic Label tracing.

### Changed
- `SKILL.md`: promoted slot count from 5 to 6. Added Categorical Semantic Tracing Rule to GATE — when `user_scale` changes, copilot must evaluate Semantic Labels before proposing a stack and halt with cloud re-routing if hardware fails label requirements.
- `script/bundle/concepts/usage_input.yaml`: added `user_scale` field with relation mapping to `always_on` / `network_accessibility`. Fixed pre-existing YAML parse error in examples sequences.

## [0.0.6] - 2026-04-02
### Changed
- `deo_resolver.py`: component-reference aware memory resolution.
  - Added `_build_comp_index()`, `_resolve_gpu_vram()`, `_resolve_sys_memory()`, `_resolve_effective_memory()` helpers.
  - `load_ontology()` now caches `_comp_index` for O(1) lookups.
  - `_extract_tags()`, `_memory_compatible()`, `build_paths_combinatorial()` all delegate to component refs with flat-field fallback for backward compatibility.
- Synced `script/bundle/` with post-migration `device.yaml`, `component.yaml`, and new `semantic_labels.yaml`.

## [0.0.5] - 2026-04-02
### Added
- Translated `SKILL.md` to English (description triggers + full body).
- Extracted reference files for progressive disclosure:
  - `references/intake-patterns.md` — per-type question sets (Explorer/Optimizer/Builder/Decider)
  - `references/cloud-deployment.md` — AWS/RunPod/Azure deployment paths
  - `references/deo-constraint-guide.md` — DEO query decomposition, scoring, and call examples
  - `references/hardware-optimization.md` — Mac mini / eGPU / OCuLink Wow Moment scripts
- Added `knowledge_advisor.py` to the Scripts section in `SKILL.md`.
- Bundle (`script/bundle/`): added `explanations` field (simple/technical) to `model` and `component` concepts for `knowledge_advisor.py` integration.

### Changed
- Slimmed `SKILL.md` from 632 → 392 lines (−38%) by moving conditional sections to references.
- Applied Fact/Semantic/Decision 3-layer reasoning rules to PROPOSE (layer table + core rule blockquote).
- Easy Mode Examples rewritten with concrete output shapes instead of vague "output direction" notes.

## [0.0.4] - 2026-04-01
### Added
- "Wow Moment" consultation logic to `SKILL.md`:
  - Proactive questioning of Mac mini preferences.
  - OCuLink-based Mini PC + RTX 3090 alternatives for mass research.
  - Automatic correction of Mac mini + eGPU misconceptions (Apple Silicon drop support).

### Changed
- Synced internal bundle (`script/bundle/`) with v0.2.0 ontology data.
- Refined consultation flow to be domain-neutral (avoiding "Ontology" over-fitting).
