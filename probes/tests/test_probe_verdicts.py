"""Regression guards: pin the exact verdict map of every probe suite.

Rationale: probes drive frameworks through scripted stubs, and a stub defect
can silently flip a verdict (observed once: a CrewAI stub substring rule
matched ReAct format instructions and finalized without acting). These guards
turn any drift -- stub bug, framework version bump, harness change -- into a
loud test failure with a readable diff instead of a quietly wrong matrix row.

Each guard subprocesses its suite exactly the way a human runs it and parses
the verdict lines, so the guard tests the whole pipeline, not internals.

Runtime: the suites contain real sleeps (cancellation/timeout probes);
the full module takes roughly 30-60 s. That is the price of guarding
end-to-end behavior; do not "optimize" it into importing internals.

Environment notes:
  - FW-A/B/C/D run in the project venv (this interpreter).
  - FW-E (crewai) lives in .venv-crewai; its guard auto-skips when crewai is
    not importable here. Run scripts/check_crewai_verdicts.py inside
    .venv-crewai to guard it.
  - FW-F (Node) auto-skips when node or probes-js/node_modules is absent.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROBES_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PROBES_DIR.parent
VERDICT_RE = re.compile(r"^(\S+)\s+-> (VIOLATION|clean/contrast)")


def run_suite(module: str) -> dict[str, str]:
    """Run a probe module in a subprocess and return {probe_name: verdict}."""
    env = dict(os.environ, PYTHONPATH="src")
    proc = subprocess.run(
        [sys.executable, "-m", module],
        cwd=PROBES_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"{module} exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    return parse_verdicts(proc.stdout)


def parse_verdicts(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = VERDICT_RE.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def test_langgraph_verdicts():
    assert run_suite("agentprobe.langgraph_probes") == {
        "sibling_leak[gate_first]": "VIOLATION",
        "sibling_leak[effect_first]": "VIOLATION",
        "replay_double_execution": "VIOLATION",
        "cancellation[sync_thread]": "VIOLATION",
        "cancellation[pure_async]": "clean/contrast",
        "timeout_zombie": "VIOLATION",
    }


def test_llamaindex_verdicts():
    assert run_suite("agentprobe.llamaindex_probes") == {
        "parallel_approval_leak": "VIOLATION",
        "timeout_zombie": "clean/contrast",
    }


def test_msaf_verdicts():
    assert run_suite("agentprobe.msaf_probes") == {
        "sibling_leak[fan_out]": "VIOLATION",
        "reject_after_effect": "VIOLATION",
        "replay[in_process_response]": "clean/contrast",
        "replay[checkpoint_restore]": "clean/contrast",
        "cancellation[sync_thread]": "VIOLATION",
        "cancellation[pure_async]": "clean/contrast",
        "timeout_zombie[host_wait_for]": "VIOLATION",
    }


def test_openai_agents_verdicts():
    assert run_suite("agentprobe.openai_agents_probes") == {
        "sibling_leak[parallel_tool_calls]": "VIOLATION",
        "reject_after_effect": "VIOLATION",
        "replay[resume_after_reject]": "clean/contrast",
        "cancellation[sync_thread]": "VIOLATION",
        "cancellation[pure_async]": "clean/contrast",
        "native_tool_timeout[sync_thread]": "clean/contrast",
        "native_tool_timeout[pure_async]": "clean/contrast",
        "timeout_zombie[host_wait_for]": "VIOLATION",
    }


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("crewai") is None,
    reason="crewai lives in .venv-crewai (see pyproject [tool.uv] conflicts); "
           "guard it there with scripts/check_crewai_verdicts.py",
    )
def test_crewai_verdicts():
    assert run_suite("agentprobe.crewai_probes") == CREWAI_EXPECTED


CREWAI_EXPECTED = {
    "review_after_effect[human_input]": "VIOLATION",
    "cancellation[kickoff_async]": "VIOLATION",
    "timeout_zombie_strict[max_execution_time]": "clean/contrast",
    "timeout_blocks_then_effect[max_execution_time]": "VIOLATION",
    "replay[checkpoint_resume]": "clean/contrast",
}


@pytest.mark.skipif(
    shutil.which("node") is None
    or not (REPO_ROOT / "probes-js" / "node_modules").exists(),
    reason="node or probes-js/node_modules absent (run: cd probes-js && npm ci)",
    )
def test_langgraph_js_verdicts():
    proc = subprocess.run(
        ["node", "langgraph_probes.mjs"],
        cwd=REPO_ROOT / "probes-js",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert parse_verdicts(proc.stdout) == {
        "sibling_leak[fan_out]": "VIOLATION",
        "reject_after_effect": "VIOLATION",
        "replay[resume_after_approve]": "VIOLATION",
        "cancellation[abort_signal]": "VIOLATION",
        "timeout_zombie[abort_timeout]": "VIOLATION",
    }