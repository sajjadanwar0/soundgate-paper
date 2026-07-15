from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import temporalio
from temporalio import activity, workflow
from temporalio.client import Client, WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError, TimeoutError as TTimeoutError
from temporalio.worker import Worker

ADDR = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233")
LOG = Path("/tmp/temporal_probe_effects.jsonl")
NO_RETRY = RetryPolicy(maximum_attempts=1)

def _server_version() -> str:
    candidates: list[str] = []
    on_path = shutil.which("temporal")

    if on_path:
        candidates.append(on_path)
    adjacent = Path(__file__).resolve().parent / "temporal"

    if adjacent.is_file() and os.access(adjacent, os.X_OK):
        candidates.append(str(adjacent))

    for c in candidates:
        try:
            out = subprocess.run([c, "--version"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
            if out:
                return out
        except OSError:
            continue
    return "temporal CLI: record manually (`temporal --version`)"

def _append(tag: str) -> None:
    with LOG.open("a") as f:
        f.write(json.dumps({"tag": tag, "t": time.time()}) + "\n")

def log_read() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]

def log_count(tag: str) -> int:
    return sum(1 for e in log_read() if e["tag"] == tag)

def log_t(tag: str) -> float | None:
    for e in log_read():
        if e["tag"] == tag:
            return e["t"]
    return None

@dataclass
class ProbeResult:
    name: str
    violation: bool
    detail: dict

    def line(self) -> str:
        status = "VIOLATION" if self.violation else "clean/contrast"
        return f"{self.name:<34} -> {status}  {self.detail}"

@activity.defn
def effect_now(tag: str) -> str:
    """The commit point: one append, exactly as the Section-3 probes."""
    _append(tag)
    return tag

@activity.defn
def blocking_effect(tag: str, delay: float) -> str:
    """Blocking tool on the worker thread pool; NO heartbeat, so Temporal's
    documented cancellation channel never reaches it."""
    _append(tag + ":started")
    time.sleep(delay)
    _append(tag)
    return tag

@activity.defn
async def heartbeating_effect(tag: str, delay: float) -> str:
    """Contrast: the same logical tool, heartbeating -- the documented way to
    receive cancellation. On cancel it commits nothing."""
    _append(tag + ":started")
    steps = int(delay / 0.1)
    for _ in range(steps):
        activity.heartbeat()
        await asyncio.sleep(0.1)
    _append(tag)
    return tag

@workflow.defn
class SiblingApprovalWorkflow:
    """T1: gated branch awaits a Signal (documented HITL pattern); sibling
    branch performs its effect. Both branches are siblings under gather."""
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
    async def run(self, tag: str) -> dict:
        async def gated() -> None:
            self._state = "awaiting_decision"
            await workflow.wait_condition(lambda: self.decision is not None)
            if self.decision:
                await workflow.execute_activity(
                    effect_now, args=[tag + ":gated"],
                    start_to_close_timeout=timedelta(seconds=5),
                    retry_policy=NO_RETRY)

        async def sibling() -> None:
            await workflow.execute_activity(
                effect_now, args=[tag + ":sibling"],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=NO_RETRY)

        await asyncio.gather(gated(), sibling())
        return {"decision": self.decision}

@workflow.defn
class ReplayWorkflow:
    """T2: effect BEFORE the approval wait; the harness forces a full-history
    replay between the effect and the decision (worker restart, cache off)."""

    def __init__(self) -> None:
        self.decision: bool | None = None

    @workflow.signal
    def decide(self, approved: bool) -> None:
        self.decision = approved

    @workflow.run
    async def run(self, tag: str) -> dict:
        await workflow.execute_activity(
            effect_now, args=[tag + ":pre_gate"],
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=NO_RETRY)
        await workflow.wait_condition(lambda: self.decision is not None)
        return {"decision": self.decision,
                "replayed": workflow.unsafe.is_replaying()}


@workflow.defn
class CancelWorkflow:
    """T3/T3b: await one activity; the harness cancels the run mid-flight."""
    @workflow.run
    async def run(self, tag: str, delay: float, heartbeating: bool) -> str:
        fn = heartbeating_effect if heartbeating else blocking_effect
        await workflow.execute_activity(
            fn, args=[tag, delay],
            start_to_close_timeout=timedelta(seconds=30),
            heartbeat_timeout=timedelta(seconds=2) if heartbeating else None,
            retry_policy=NO_RETRY)
        return "done"


@workflow.defn
class TimeoutWorkflow:
    """T4: the activity outlives its start_to_close deadline."""
    @workflow.run
    async def run(self, tag: str, delay: float, deadline_s: float) -> str:
        try:
            await workflow.execute_activity(
                blocking_effect, args=[tag, delay],
                start_to_close_timeout=timedelta(seconds=deadline_s),
                retry_policy=NO_RETRY)
            return "completed"
        except ActivityError as e:
            if isinstance(e.cause, TTimeoutError):
                return "timeout_observed"
            raise

def make_worker(client: Client, tq: str) -> Worker:
    return Worker(
        client, task_queue=tq,
        workflows=[SiblingApprovalWorkflow, ReplayWorkflow,
                   CancelWorkflow, TimeoutWorkflow],
        activities=[effect_now, blocking_effect, heartbeating_effect],
        activity_executor=ThreadPoolExecutor(4),
        max_cached_workflows=0,
    )


async def probe_t1_sibling(client: Client) -> list[ProbeResult]:
    tq, tag = "tq-t1", "t1"
    worker = make_worker(client, tq)

    async with worker:
        h = await client.start_workflow(
            SiblingApprovalWorkflow.run, args=[tag],
            id=f"wf-t1-{time.time_ns()}", task_queue=tq)
        deadline = time.time() + 10

        while time.time() < deadline and log_count(tag + ":sibling") == 0:
            await asyncio.sleep(0.05)
        state_at_effect = await h.query(SiblingApprovalWorkflow.state)
        t_effect = log_t(tag + ":sibling")
        sibling_during_pause = (
                t_effect is not None and state_at_effect == "awaiting_decision")
        t_reject = time.time()

        await h.signal(SiblingApprovalWorkflow.decide, False)  # REJECT

        await h.result()

    gated_ran = log_count(tag + ":gated") > 0
    reject_after_effect = sibling_during_pause and not gated_ran \
                          and t_effect is not None and t_effect < t_reject

    return [
        ProbeResult("T1 sibling approval leak", sibling_during_pause, {
            "sibling_effects": log_count(tag + ":sibling"),
            "state_when_effect_seen": state_at_effect,
            "t_effect<t_reject": (t_effect or 0) < t_reject}),
        ProbeResult("T1 reject-after-effect", reject_after_effect, {
            "gated_effect_ran": gated_ran,
            "sibling_already_committed": sibling_during_pause}),
    ]


async def probe_t2_replay(client: Client) -> ProbeResult:
    tq, tag = "tq-t2", "t2"
    w1 = make_worker(client, tq)
    t1 = asyncio.create_task(w1.run())
    h = await client.start_workflow(
        ReplayWorkflow.run, args=[tag], id=f"wf-t2-{time.time_ns()}", task_queue=tq)
    deadline = time.time() + 10

    while time.time() < deadline and log_count(tag + ":pre_gate") == 0:
        await asyncio.sleep(0.05)
    pre = log_count(tag + ":pre_gate")
    await w1.shutdown()

    await t1

    await h.signal(ReplayWorkflow.decide, True)

    w2 = make_worker(client, tq)

    async with w2:
        res = await h.result()
    post = log_count(tag + ":pre_gate")
    return ProbeResult("T2 replay double-execution", post > pre, {
        "pre_gate_effects_before_resume": pre,
        "after_resume": post,
        "workflow_reports_replayed": res.get("replayed")})

async def probe_t3_cancel(client: Client, heartbeating: bool) -> ProbeResult:
    tq = f"tq-t3{'b' if heartbeating else ''}"
    tag = f"t3{'b' if heartbeating else ''}"
    worker = make_worker(client, tq)

    async with worker:
        h = await client.start_workflow(
            CancelWorkflow.run, args=[tag, 2.0, heartbeating],
            id=f"wf-{tag}-{time.time_ns()}", task_queue=tq)
        deadline = time.time() + 10

        while time.time() < deadline and log_count(tag + ":started") == 0:
            await asyncio.sleep(0.05)

        await h.cancel()

        observed = None

        try:
            await h.result()
        except WorkflowFailureError as e:
            observed = type(e.cause).__name__
        t_obs = time.time()

        await asyncio.sleep(2.5)

    t_effect = log_t(tag)
    orphan = t_effect is not None and t_effect > t_obs
    name = ("T3b cancel: heartbeating (contrast)" if heartbeating
            else "T3 cancel orphan: no heartbeat")

    return ProbeResult(name, orphan, {
        "caller_observed": observed,
        "effect_committed": log_count(tag),
        "effect_after_cancel_observed": orphan})

async def probe_t4_timeout(client: Client) -> ProbeResult:
    tq, tag = "tq-t4", "t4"
    worker = make_worker(client, tq)

    async with worker:
        h = await client.start_workflow(
            TimeoutWorkflow.run, args=[tag, 2.0, 1.0],
            id=f"wf-t4-{time.time_ns()}", task_queue=tq)
        res = await h.result()
        t_obs = time.time()
        await asyncio.sleep(2.5)  # let the zombie land

    t_effect = log_t(tag)
    zombie = res == "timeout_observed" and t_effect is not None \
             and t_effect > t_obs

    return ProbeResult("T4 timeout zombie", zombie, {
        "caller_saw": res,
        "effect_committed": log_count(tag),
        "effect_after_timeout_observed": zombie})

async def main() -> int:
    LOG.unlink(missing_ok=True)
    server_ver = _server_version()
    print("== T-PROBES: Temporal contrast arm ==")
    print(f"pinned: temporalio (Python SDK) {temporalio.__version__}; "
          f"{server_ver}")
    print(f"python {sys.version.split()[0]}; predicates: Section 3.2, "
          f"evaluated at the commit point (activity effect-log append); "
          f"RetryPolicy(maximum_attempts=1) on every activity\n")

    client = await Client.connect(ADDR)
    results: list[ProbeResult] = []
    results += await probe_t1_sibling(client)
    results.append(await probe_t2_replay(client))
    results.append(await probe_t3_cancel(client, heartbeating=False))
    results.append(await probe_t3_cancel(client, heartbeating=True))
    results.append(await probe_t4_timeout(client))

    print("\n".join(r.line() for r in results))
    v = sum(r.violation for r in results)
    print(f"\nBEHAVIORAL VIOLATION BITS: {v}/{len(results)} "
          f"(contrast arm; excluded from all recurrence denominators)")
    print("NOTE: the T1 bit is behavioral only -- Temporal's documentation "
          "does not imply a cross-branch pause, so no contract-mismatch "
          "claim attaches to it; T3's cooperative-cancellation and T4's "
          "may-still-be-running behaviors are vendor-documented.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))