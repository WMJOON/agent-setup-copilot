from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ESTIMATOR_PATH = REPO_ROOT / "skills" / "agent-setup-copilot" / "script" / "estimator.py"
SKILL_PATH = REPO_ROOT / "skills" / "agent-setup-copilot" / "SKILL.md"


def load_estimator_module():
    spec = importlib.util.spec_from_file_location("agent_setup_estimator", ESTIMATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def run_estimator(*args: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(ESTIMATOR_PATH), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
