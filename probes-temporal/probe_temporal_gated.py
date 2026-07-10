"""T5: SOUNDGATE composed at Temporal's activity boundary (repaired T1 twin).

Scenario A of the framework integrations, transplanted: the same
gated-signal + sibling-effect workflow as probe T1, but the sibling's effect
is routed through the gate's ~20-line wrapper (submit; perform ONLY on
release). Expected under the paper's P1/P2:

  MEDIATED RUN : sibling submits with needs_approval=True -> held during the
                 signal pause -> operator REJECTS -> zero effects; a zombie
                 resubmission meets refused (sticky, P2).
  CONTROL RUN  : an un-gated mediated effect (needs_approval=False) on a
                 fresh identity releases and executes -- the gate is not
                 refusing everything.

Scope, stated so the bit is not over-read: this composes the gate's
hold/reject path on Temporal; the approve-path choreography and the full
verdict set are the existing Table 9 evidence, unchanged by the host engine.
Gate: the published package's in-process `Gate` (pip install soundgate,
PyO3 binding of the verified core) by default; set SOUNDGATE_ADDR to drive
the external socket gate instead (the paper-preferred deployment mode).

  temporal server start-dev --headless --ip 127.0.0.1 --port 7233
  python probe_temporal_gated.py
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import temporalio
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

with workflow.unsafe.imports_passed_through():
    import soundgate

ADDR = "127.0.0.1:7233"
LOG = Path("/tmp/temporal_gated_effects.jsonl")
NO_RETRY = RetryPolicy(maximum_attempts=1)

# One gate for the process, constructed lazily so the workflow sandbox's
# module re-import performs no side effects. Activities run in this same
# worker process, so the in-process Gate is shared exactly as an external
# gate would be reachable.
_GATE = None


def _gate():
    global _GATE
    if _GATE is None:
        addr = os.environ.get("SOUNDGATE_ADDR")
        _GATE = soundgate.GateClient(addr) if addr else soundgate.Gate()
    return _GATE


def _append(tag: str) -> None:
    with LOG.open("a") as f:
        f.write(json.dumps({"tag": tag, "t": time.time()}) + "\n")


def _count(tag: str) -> int:
    if not LOG.exists():
        return 0
    return sum(1 for l in LOG.read_text().splitlines()
               if l.strip() and json.loads(l)["tag"] == tag)


# --------------------- the integration surface (verbatim shape) ------------
def mediated_effect(run_id: str, effect_key: str, do_effect,
                    needs_approval: bool = False) -> str:
    """The whole integration contract, as in every framework integration:
    submit the identity; perform the effect only on release."""
    v = _gate().submit(run_id, effect_key, needs_approval)
    if v.released:
        do_effect()
    return str(v)


@activity.defn
def gated_sibling_effect(run_id: str, tag: str) -> str:
    return mediated_effect(run_id, tag, lambda: _append(tag),
                           needs_approval=True)


@activity.defn
def ungated_control_effect(run_id: str, tag: str) -> str:
    return mediated_effect(run_id, tag, lambda: _append(tag),
                           needs_approval=False)


@workflow.defn
class GatedSiblingWorkflow:
    def __init__(self) -> None:
        self.decision: bool | None = None
        self._state = "starting"

    @workflow.signal
    def decide(self, approved: bool) -> None:
        self.decision = approved

    @workflow.query
    def state(self) -> str:
        return self._state

    @workflow.run
    async def run(self, run_id: str, tag: str, gated: bool) -> dict:
        async def approval_branch() -> None:
            self._state = "awaiting_decision"
            await workflow.wait_condition(lambda: self.decision is not None)

        async def sibling_branch() -> str:
            fn = gated_sibling_effect if gated else ungated_control_effect
            return await workflow.execute_activity(
                fn, args=[run_id, tag],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=NO_RETRY)

        _, verdict = await asyncio.gather(approval_branch(), sibling_branch())
        return {"decision": self.decision, "sibling_verdict": verdict}


async def main() -> int:
    LOG.unlink(missing_ok=True)
    mode = f"external GateClient {os.environ.get('SOUNDGATE_ADDR')}" if os.environ.get("SOUNDGATE_ADDR") \
        else "in-process Gate (pip install soundgate)"
    print("== T5: SOUNDGATE on Temporal (repaired T1 twin) ==")
    print(f"pinned: temporalio {temporalio.__version__}; gate mode: {mode}\n")

    client = await Client.connect(ADDR)
    worker = Worker(client, task_queue="tq-t5",
                    workflows=[GatedSiblingWorkflow],
                    activities=[gated_sibling_effect, ungated_control_effect],
                    activity_executor=ThreadPoolExecutor(4),
                    max_cached_workflows=0)

    checks: list[tuple[str, bool, str]] = []
    async with worker:
        # ---- mediated run: held during pause, operator rejects ----
        run_id, tag = "t5-run", "t5:sibling"
        h = await client.start_workflow(GatedSiblingWorkflow.run,
                                        args=[run_id, tag, True],
                                        id=f"wf-t5-{time.time_ns()}", task_queue="tq-t5")
        # wait for the genuine pause, then for the sibling's submit to land
        deadline = time.time() + 10
        while time.time() < deadline and \
                await h.query(GatedSiblingWorkflow.state) != "awaiting_decision":
            await asyncio.sleep(0.05)
        while time.time() < deadline and _gate().pending_count() == 0:
            await asyncio.sleep(0.05)
        held_during_pause = (_gate().pending_count() == 1
                             and _count(tag) == 0)
        checks.append(("sibling HELD during signal pause (P1)",
                       held_during_pause,
                       f"pending={_gate().pending_count()} effects={_count(tag)}"))
        v_reject = _gate().decide(run_id, tag, False)       # operator REJECT
        v_zombie = _gate().submit(run_id, tag, True)        # late resubmission
        await h.signal(GatedSiblingWorkflow.decide, False)  # unblock the run
        res = await h.result()
        checks.append(("rejection recorded; zombie resubmit refused (P2)",
                       v_zombie.refused and _count(tag) == 0
                       and "held" in res["sibling_verdict"],
                       f"decide={v_reject} resubmit={v_zombie} "
                       f"sibling_verdict={res['sibling_verdict']} "
                       f"effects={_count(tag)}"))

        # ---- control run: mediated but un-gated effect releases ----
        c_run, c_tag = "t5-ctl", "t5:control"
        h2 = await client.start_workflow(GatedSiblingWorkflow.run,
                                         args=[c_run, c_tag, False],
                                         id=f"wf-t5c-{time.time_ns()}", task_queue="tq-t5")
        await h2.signal(GatedSiblingWorkflow.decide, True)
        res2 = await h2.result()
        checks.append(("legitimate mediated effect releases and executes",
                       "release" in res2["sibling_verdict"]
                       and _count(c_tag) == 1,
                       f"verdict={res2['sibling_verdict']} effects={_count(c_tag)}"))

    ok = all(c[1] for c in checks)
    for name, passed, detail in checks:
        print(f"{name:<48} -> {'PASS' if passed else 'FAIL'}  {detail}")
    verdict = ("REPAIRED (0 effects under pause+reject; control released)"
               if ok else "FAILED")
    print(f"\nT5 VERDICT: {verdict}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))