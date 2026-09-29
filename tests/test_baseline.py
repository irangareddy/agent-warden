"""Checks for the baseline comparison evaluation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.baseline import wilson_interval  # noqa: E402


_, zero_of_40_upper = wilson_interval(0, 40)
fifteen_of_15_lower, _ = wilson_interval(15, 15)
assert abs(zero_of_40_upper - 0.0876) < 0.002, zero_of_40_upper
assert abs(fifteen_of_15_lower - 0.796) < 0.002, fifteen_of_15_lower

completed = subprocess.run(
    [sys.executable, str(ROOT / "eval" / "baseline.py")],
    cwd=ROOT,
    capture_output=True,
    text=True,
)
assert completed.returncode == 0, completed.stdout + completed.stderr
assert "| Plain denylist |" in completed.stdout
assert "| Wagent default |" in completed.stdout
assert "| Wagent default + beet |" in completed.stdout
assert completed.stdout.rstrip().endswith("not real-world accuracy.")

print("baseline tests passed")
