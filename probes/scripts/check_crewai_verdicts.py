"""Verdict regression guard for the FW-E (crewai) suite.

crewai lives in its own environment (.venv-crewai; see pyproject.toml
[tool.uv] conflicts), so the main pytest guard auto-skips it. Run this
inside that environment instead:

    CREWAI_DISABLE_TELEMETRY=true OTEL_SDK_DISABLED=true \
      UV_PROJECT_ENVIRONMENT=.venv-crewai uv run --no-sync \
      python scripts/check_crewai_verdicts.py

Exit code 0 = verdict map matches the pinned snapshot; 1 = drift (diff
printed). Same parsing as tests/test_probe_verdicts.py on purpose.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PROBES_DIR = Path(__file__).resolve().parents[1]
VERDICT_RE = re.compile(r"^(\S+)\s+-> (VIOLATION|clean/contrast)")

EXPECTED = {
    "review_after_effect[human_input]": "VIOLATION",
    "cancellation[kickoff_async]": "VIOLATION",
    "timeout_zombie_strict[max_execution_time]": "clean/contrast",
    "timeout_blocks_then_effect[max_execution_time]": "VIOLATION",
    "replay[checkpoint_resume]": "clean/contrast",
}


def main() -> int:
    env = dict(
        os.environ,
        PYTHONPATH="src",
        CREWAI_DISABLE_TELEMETRY="true",
        OTEL_SDK_DISABLED="true",
        CREWAI_TESTING="true",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "agentprobe.crewai_probes"],
        cwd=PROBES_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        print(f"FAIL: suite exited {proc.returncode}")
        return 1
    got = {
        m.group(1): m.group(2)
        for line in proc.stdout.splitlines()
        if (m := VERDICT_RE.match(line.strip()))
    }
    if got == EXPECTED:
        print(f"OK: crewai verdict map matches snapshot ({len(got)} probes)")
        return 0
    print("VERDICT DRIFT DETECTED")
    for k in sorted(set(EXPECTED) | set(got)):
        e, g = EXPECTED.get(k, "<absent>"), got.get(k, "<absent>")
        if e != g:
            print(f"  {k}: expected {e}, got {g}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())