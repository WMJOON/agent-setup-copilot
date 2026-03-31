#!/usr/bin/env python3
"""
Sync selected ontology source-of-truth files into the copilot bundle snapshot
and local cache, then optionally run a lightweight smoke test.

Usage:
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py --smoke-test
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py \
    --ontology-dir /path/to/agent-setup-ontology
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

FILES_TO_SYNC = [
    "concepts/api_service.yaml",
    "concepts/relation.yaml",
    "instances/api_service.yaml",
    "instances/relation.yaml",
]

DEFAULT_ONTOLOGY_DIR = Path(
    "/Users/wmjoon/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
    "wmjoon/10_Agent_KnowledgeBase/project/local-agent-advisor/agent-setup-ontology"
)


def sync_files(ontology_dir: Path, copilot_root: Path, cache_dir: Path) -> list[tuple[Path, Path]]:
    bundle_root = copilot_root / "skills" / "agent-setup-copilot" / "script" / "bundle"
    synced: list[tuple[Path, Path]] = []

    for rel in FILES_TO_SYNC:
        src = ontology_dir / rel
        if not src.exists():
            raise FileNotFoundError(f"Missing ontology source file: {src}")

        for dst_root in [bundle_root, cache_dir]:
            dst = dst_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            synced.append((src, dst))

    return synced


def run_smoke_test(copilot_root: Path) -> int:
    script = copilot_root / "skills" / "agent-setup-copilot" / "script" / "transition.py"
    cmd = [
        sys.executable,
        str(script),
        "--api",
        "gemini-3-flash",
        "--monthly-cost",
        "55",
        "--growth",
        "10",
    ]
    result = subprocess.run(cmd, cwd=str(copilot_root), capture_output=True, text=True)
    print("# --- smoke test stdout ---")
    print(result.stdout.strip())
    if result.stderr.strip():
        print("# --- smoke test stderr ---")
        print(result.stderr.strip())
    return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync ontology files into copilot bundle/cache")
    parser.add_argument("--ontology-dir", type=Path, default=DEFAULT_ONTOLOGY_DIR)
    parser.add_argument(
        "--copilot-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="Path to agent-setup-copilot repo root",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "agent-setup-copilot",
    )
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()

    synced = sync_files(args.ontology_dir, args.copilot_root, args.cache_dir)
    print(f"Synced {len(synced)} file copies")
    for src, dst in synced:
        print(f"- {src} -> {dst}")

    if args.smoke_test:
        rc = run_smoke_test(args.copilot_root)
        sys.exit(rc)
