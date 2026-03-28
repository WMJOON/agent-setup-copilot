#!/usr/bin/env python3
"""
Ontology + concepts loader — outputs both to stdout for Claude to read.

Priority order (per file):
  1. AGENT_COPILOT_ONTOLOGY_URL / AGENT_COPILOT_CONCEPTS_URL env override
  2. agent-setup-ontology GitHub raw fetch
  3. Local cache (~/.cache/agent-setup-copilot/)
  4. Bundle fallback (copilot/bundle/)

Usage:
  python3 copilot/loader.py           # print ontology + concepts
  python3 copilot/loader.py --update  # force refresh cache then print
"""

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

_BASE = "https://raw.githubusercontent.com/WMJOON/agent-setup-ontology/main"

ONTOLOGY_URL  = os.getenv("AGENT_COPILOT_ONTOLOGY_URL",  f"{_BASE}/ontology.yaml")
CONCEPTS_URL  = os.getenv("AGENT_COPILOT_CONCEPTS_URL",  f"{_BASE}/concepts.yaml")
RELATIONS_URL = os.getenv("AGENT_COPILOT_RELATIONS_URL", f"{_BASE}/relations.yaml")

CACHE_DIR  = Path.home() / ".cache" / "agent-setup-copilot"
BUNDLE_DIR = Path(__file__).parent / "bundle"
CACHE_TTL  = 60 * 60 * 24  # 24 hours

_FILES = {
    "ontology":  (ONTOLOGY_URL,  CACHE_DIR / "ontology.yaml",  BUNDLE_DIR / "ontology.yaml"),
    "concepts":  (CONCEPTS_URL,  CACHE_DIR / "concepts.yaml",  BUNDLE_DIR / "concepts.yaml"),
    "relations": (RELATIONS_URL, CACHE_DIR / "relations.yaml", BUNDLE_DIR / "relations.yaml"),
}


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
    parser = argparse.ArgumentParser(description="Load ontology + concepts for Claude")
    parser.add_argument("--update", action="store_true", help="Force cache refresh")
    args = parser.parse_args()

    try:
        data = load_all(force_update=args.update)
        print("# === ONTOLOGY ===")
        print(yaml.dump(data["ontology"],  allow_unicode=True, default_flow_style=False))
        print("# === CONCEPTS ===")
        print(yaml.dump(data["concepts"],  allow_unicode=True, default_flow_style=False))
        print("# === RELATIONS ===")
        print(yaml.dump(data["relations"], allow_unicode=True, default_flow_style=False))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
