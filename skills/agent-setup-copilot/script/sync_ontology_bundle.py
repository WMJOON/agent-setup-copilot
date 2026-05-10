#!/usr/bin/env python3
"""
Sync selected ontology source-of-truth files into the copilot bundle snapshot
and local cache, then optionally run a lightweight smoke test.

By default, fetches from GitHub (WMJOON/agent-setup-ontology@main) over HTTPS.
Pass --ontology-dir to use a local checkout instead.

Usage:
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py --smoke-test
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py \
    --ontology-repo WMJOON/agent-setup-ontology --ontology-ref main
  python3 skills/agent-setup-copilot/script/sync_ontology_bundle.py \
    --ontology-dir /path/to/agent-setup-ontology
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

FILES_TO_SYNC = [
    "concepts/api_service.yaml",
    "concepts/relation.yaml",
    "instances/api_service.yaml",
    "instances/relation.yaml",
]

DEFAULT_ONTOLOGY_REPO = "WMJOON/agent-setup-ontology"
DEFAULT_ONTOLOGY_REF = "main"
RAW_BASE = "https://raw.githubusercontent.com"


def _bundle_and_cache_targets(
    rel: str, copilot_root: Path, cache_dir: Path
) -> list[Path]:
    bundle_root = copilot_root / "skills" / "agent-setup-copilot" / "script" / "bundle"
    return [bundle_root / rel, cache_dir / rel]


def sync_files_from_dir(
    ontology_dir: Path, copilot_root: Path, cache_dir: Path
) -> list[tuple[str, Path]]:
    synced: list[tuple[str, Path]] = []
    for rel in FILES_TO_SYNC:
        src = ontology_dir / rel
        if not src.exists():
            raise FileNotFoundError(f"Missing ontology source file: {src}")
        for dst in _bundle_and_cache_targets(rel, copilot_root, cache_dir):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            synced.append((str(src), dst))
    return synced


def sync_files_from_github(
    repo: str, ref: str, copilot_root: Path, cache_dir: Path
) -> list[tuple[str, Path]]:
    synced: list[tuple[str, Path]] = []
    for rel in FILES_TO_SYNC:
        url = f"{RAW_BASE}/{repo}/{ref}/{rel}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as e:
            raise FileNotFoundError(
                f"Missing ontology source file at {url} (HTTP {e.code})"
            ) from e
        for dst in _bundle_and_cache_targets(rel, copilot_root, cache_dir):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(payload)
            synced.append((url, dst))
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
    parser.add_argument(
        "--ontology-dir",
        type=Path,
        default=None,
        help="Local checkout of agent-setup-ontology. If omitted, fetch from GitHub.",
    )
    parser.add_argument(
        "--ontology-repo",
        default=DEFAULT_ONTOLOGY_REPO,
        help=f"GitHub <owner>/<repo> for the ontology SOT (default: {DEFAULT_ONTOLOGY_REPO})",
    )
    parser.add_argument(
        "--ontology-ref",
        default=DEFAULT_ONTOLOGY_REF,
        help=f"Git ref (branch / tag / sha) to fetch (default: {DEFAULT_ONTOLOGY_REF})",
    )
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

    if args.ontology_dir is not None:
        synced = sync_files_from_dir(args.ontology_dir, args.copilot_root, args.cache_dir)
        source_label = f"local: {args.ontology_dir}"
    else:
        synced = sync_files_from_github(
            args.ontology_repo, args.ontology_ref, args.copilot_root, args.cache_dir
        )
        source_label = f"github: {args.ontology_repo}@{args.ontology_ref}"

    print(f"Synced {len(synced)} file copies from {source_label}")
    for src, dst in synced:
        print(f"- {src} -> {dst}")

    if args.smoke_test:
        rc = run_smoke_test(args.copilot_root)
        sys.exit(rc)
