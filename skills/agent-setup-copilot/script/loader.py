#!/usr/bin/env python3
"""
Ontology loader — fetches concepts + instances from agent-setup-ontology
and outputs them to stdout for Claude to read.

The ontology repo uses a per-entity directory layout:

    concepts/           ← semantic definitions (what fields mean)
      use_case.yaml, device.yaml, model.yaml, framework.yaml,
      api_service.yaml, component.yaml, repo.yaml, setup_profile.yaml,
      cost_estimation.yaml, usage_input.yaml, relation.yaml

    instances/          ← actual data (devices, models, frameworks, …)
      use_case.yaml, device.yaml, model.yaml, framework.yaml,
      api_service.yaml, component.yaml, repo.yaml, setup_profile.yaml,
      relation.yaml

Priority order (per file):
  1. Environment variable override (AGENT_COPILOT_BASE_URL)
  2. agent-setup-ontology GitHub raw fetch
  3. Local cache (~/.cache/agent-setup-copilot/)
  4. Bundle fallback (script/bundle/)

Usage:
  python3 skills/agent-setup-copilot/script/loader.py
  python3 skills/agent-setup-copilot/script/loader.py --update
"""

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

_BASE = os.getenv(
    "AGENT_COPILOT_BASE_URL",
    "https://raw.githubusercontent.com/WMJOON/agent-setup-ontology/main",
)

CACHE_DIR = Path.home() / ".cache" / "agent-setup-copilot"
BUNDLE_DIR = Path(__file__).parent / "bundle"
CACHE_TTL = 60 * 60 * 24  # 24 hours

# Entity names shared by both concepts/ and instances/
_SHARED_ENTITIES = [
    "use_case",
    "device",
    "model",
    "framework",
    "api_service",
    "component",
    "repo",
    "setup_profile",
    "relation",
    "cost_estimation",  # schema in concepts/, data (token profiles, thresholds) in instances/
]

# Entities that only exist in concepts/
_CONCEPTS_ONLY = [
    "usage_input",
]

# Build file map: (url, cache_path, bundle_path)
_FILES: dict[str, tuple[str, Path, Path]] = {}

for entity in _SHARED_ENTITIES:
    _FILES[f"concepts/{entity}"] = (
        f"{_BASE}/concepts/{entity}.yaml",
        CACHE_DIR / "concepts" / f"{entity}.yaml",
        BUNDLE_DIR / "concepts" / f"{entity}.yaml",
    )
    _FILES[f"instances/{entity}"] = (
        f"{_BASE}/instances/{entity}.yaml",
        CACHE_DIR / "instances" / f"{entity}.yaml",
        BUNDLE_DIR / "instances" / f"{entity}.yaml",
    )

for entity in _CONCEPTS_ONLY:
    _FILES[f"concepts/{entity}"] = (
        f"{_BASE}/concepts/{entity}.yaml",
        CACHE_DIR / "concepts" / f"{entity}.yaml",
        BUNDLE_DIR / "concepts" / f"{entity}.yaml",
    )


def load_all(force_update: bool = False) -> dict[str, dict]:
    return {name: _load_one(name, force_update) for name in _FILES}


def _load_one(name: str, force_update: bool) -> dict:
    url, cache, bundle = _FILES[name]

    if force_update or _stale(cache):
        data = _fetch(url)
        if data:
            _write_cache(cache, data)
            return data

    if cache.exists():
        return _read(cache)

    if bundle.exists():
        return _read(bundle)

    raise FileNotFoundError(
        f"{name} not found. Run with --update or check internet connection."
    )


def _stale(path: Path) -> bool:
    return not path.exists() or (time.time() - path.stat().st_mtime) > CACHE_TTL


def _fetch(url: str) -> dict | None:
    try:
        import httpx
        r = httpx.get(url, timeout=5, follow_redirects=True)
        r.raise_for_status()
        return yaml.safe_load(r.text)
    except Exception:
        return None


def _write_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load ontology for Claude")
    parser.add_argument("--update", action="store_true", help="Force cache refresh")
    args = parser.parse_args()

    try:
        data = load_all(force_update=args.update)

        # Group and print concepts
        print("# === CONCEPTS ===")
        for key in sorted(k for k in data if k.startswith("concepts/")):
            entity = key.split("/", 1)[1]
            print(f"\n# --- {entity} ---")
            print(yaml.dump(data[key], allow_unicode=True, default_flow_style=False))

        # Group and print instances
        print("# === INSTANCES ===")
        for key in sorted(k for k in data if k.startswith("instances/")):
            entity = key.split("/", 1)[1]
            print(f"\n# --- {entity} ---")
            print(yaml.dump(data[key], allow_unicode=True, default_flow_style=False))

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
