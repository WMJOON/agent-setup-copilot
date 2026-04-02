# Changelog
All notable changes to this project will be documented in this file.

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
