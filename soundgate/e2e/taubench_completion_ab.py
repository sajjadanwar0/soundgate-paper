#!/usr/bin/env python3
"""taubench_completion_ab.py -- P6: does SOUNDGATE break legitimate task
completion, and what does it cost end-to-end?

Runs tau-bench (Sierra) retail/airline episodes to COMPLETION under two arms:

  nogate  tau-bench's own tool execution (first call executed, tau-bench
          semantics -- identical to taubench_exposure.py's loop).
  gate    identical, except every CONSEQUENTIAL (write) tool call is routed
          through the live SOUNDGATE with AUTO-APPROVE before it executes:
              submit(needs_approval=True) -> decide(approved=True) -> release
          and only then does env.step() perform the write. Auto-approve makes
          the gate TRANSPARENT to a legitimate task: the same write executes,
          so any difference in tau-bench reward is model nondeterminism, not the
          gate. A write that fails to release is a FALSE POSITIVE (fail-closed),
          which must be 0.

Per arm we record tau-bench success (reward), episode wall-clock latency, writes
gated, and fail-closed count; then we report the A/B delta: success parity
(Delta ~ 0), latency overhead (the cost), and fail-closed (must be 0).

This answers reviewer R3's Sec 5.5 ("does the agent still solve tasks? what is
the overhead? does the gate ever fail-closed incorrectly?") on a THIRD-PARTY
benchmark we did not author -- not the paper's own task battery.

KEYING. Each write is keyed uniquely per (env, task, turn, tool), so the gate's
idempotent dedup never fires within an episode. Dedup is verified separately in
the paper (Loom + differential conformance); here we isolate the one question
P6 asks: does putting the gate in the effect path break or slow a legitimate run.

DETERMINISM. Run both arms at --temperature 0. At temp 0 the agent and the
user-simulator are near-deterministic, so the two arms produce the same
trajectory except for the gate round-trip; per-task reward should match exactly
and any divergence is model noise. Latency delta is then the pure gate overhead.

RUN (needs tau-bench importable + a provider key; build the gate first):
    cd soundgate && cargo build --release
    export PYTHONPATH=/path/to/tau-bench          # the cloned sierra-research/tau-bench
    export OPENAI_API_KEY=...                       # or ANTHROPIC_API_KEY=...
    python e2e/taubench_completion_ab.py --env retail --provider openai \
        --model gpt-4o --user-model gpt-4o-mini --start 0 --end 20 --arm both \
        --out results/p6_completion_retail_gpt4o.jsonl

Start with --end 20 for a first signal (episodes are multi-turn; cost scales with
tasks * turns * two models, and --arm both runs each task TWICE). Resume-safe:
re-running with the same --out skips (arm, task_index) already recorded.

Self-test (offline, no API, validates both arms + gate transparency):
    python e2e/taubench_completion_ab.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
BIN = HERE.parents[1] / "target" / "release" / "soundgate"  # soundgate/target/release/soundgate

# ---- tool classification per domain (identical to taubench_exposure.py) ------
CONSEQUENTIAL = {
    "retail": {
        "cancel_pending_order", "exchange_delivered_order_items",
        "modify_pending_order_address", "modify_pending_order_items",
        "modify_pending_order_payment", "modify_user_address",
        "return_delivered_order_items",
    },
    "airline": {
        "book_reservation", "cancel_reservation", "send_certificate",
        "update_reservation_baggages", "update_reservation_flights",
        "update_reservation_passengers",
    },
}


# ---- the live gate client (same line protocol as the other e2e harnesses) ----
class GateClient:
    def __init__(self, addr):
        self.s = socket.create_connection(addr, timeout=5)
        self.r = self.s.makefile("r")
        self.lock = threading.Lock()

    def _c(self, req):
        with self.lock:
            self.s.sendall((json.dumps(req) + "\n").encode())
            return json.loads(self.r.readline())["verdict"]

    def submit(self, run, key, needs_approval):
        return self._c({"op": "submit", "run_id": run, "effect_key": key,
                        "needs_approval": needs_approval})

    def decide(self, run, key, approved):
        return self._c({"op": "decide", "run_id": run, "effect_key": key,
                        "approved": approved})

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


# ---- model completion: real (litellm, same as taubench_exposure.py) ----------
def complete_real(messages, model, provider, tools_info, temperature):
    from litellm import completion
    res = completion(messages=messages, model=model, custom_llm_provider=provider,
                     tools=tools_info, temperature=temperature)
    return res.choices[0].message.model_dump()


class MockModel:
    """Offline scripted retail episode for --self-test: a benign parallel batch,
    then a batch mixing a benign read with a consequential write (the write the
    gate arm must route and release), then a text turn to end. No API."""
    def __init__(self):
        self.turn = 0

    def __call__(self, messages, model, provider, tools_info, temperature):
        self.turn += 1

        def tc(i, name, args):
            return {"id": f"c{i}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)}}
        if self.turn == 1:
            return {"role": "assistant", "content": None, "tool_calls": [
                tc(0, "get_order_details", {"order_id": "#W2378156"})]}
        if self.turn == 2:
            return {"role": "assistant", "content": None, "tool_calls": [
                tc(0, "exchange_delivered_order_items",
                   {"order_id": "#W2378156", "item_ids": ["1151293680"],
                    "new_item_ids": ["4983901480"], "payment_method_id": "credit_card_9513926"})]}
        return {"role": "assistant", "content": "All set -- anything else?", "tool_calls": None}


# ---- one episode to completion, under one arm --------------------------------
def run_episode_ab(env, complete, model, provider, tools_info, env_name,
                   task_index, max_turns, temperature, gate, arm):
    from tau_bench.types import Action, RESPOND_ACTION_NAME
    obs = env.reset(task_index=task_index).observation
    messages = [{"role": "system", "content": env.wiki},
                {"role": "user", "content": obs}]
    run_id = f"p6-{env_name}-{task_index}"
    t0 = time.monotonic()
    last_reward = 0.0
    n_writes = n_gated = fail_closed = 0
    gate_wait_s = 0.0
    done = False
    for turn in range(max_turns):
        msg = complete(messages, model, provider, tools_info, temperature)
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            first = tool_calls[0]                 # tau-bench executes the first only
            name = first["function"]["name"]
            try:
                kwargs = json.loads(first["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                kwargs = {}
            is_write = name in CONSEQUENTIAL.get(env_name, set())
            blocked = False
            if is_write:
                n_writes += 1
                if gate is not None and arm == "gate":
                    key = f"{env_name}:{task_index}:t{turn}:{name}"
                    g0 = time.monotonic()
                    gate.submit(run_id, key, True)          # -> held_for_approval
                    v = gate.decide(run_id, key, True)      # AUTO-APPROVE -> release
                    gate_wait_s += time.monotonic() - g0
                    n_gated += 1
                    if v != "release":                      # false positive: never expected
                        fail_closed += 1
                        blocked = True
            msg["tool_calls"] = tool_calls[:1]
            messages.append(msg)
            if blocked:
                # the gate refused a legitimate write: the effect does NOT execute.
                # feed an error observation so the end-to-end consequence is visible.
                messages.append({"role": "tool", "tool_call_id": first["id"],
                                 "name": name, "content": "ERROR: effect blocked by admission gate"})
                continue
            resp = env.step(Action(name=name, kwargs=kwargs))
            messages.append({"role": "tool", "tool_call_id": first["id"],
                             "name": name, "content": resp.observation})
        else:
            resp = env.step(Action(name=RESPOND_ACTION_NAME,
                                   kwargs={"content": msg.get("content") or ""}))
            messages.append(msg)
            messages.append({"role": "user", "content": resp.observation})
        # tau-bench's EnvResponse carries reward (0 until done, then the episode
        # reward). Fall back to env.reward for older API variants.
        r = getattr(resp, "reward", None)
        if r is None:
            r = getattr(env, "reward", None)
        if r is not None:
            last_reward = float(r)
        if getattr(resp, "done", False):
            done = True
            break
    return {
        "experiment": "P6-COMPLETION-AB", "env": env_name, "arm": arm,
        "task_index": task_index, "model": model,
        "reward": float(last_reward), "done": done,
        "wall_s": round(time.monotonic() - t0, 3),
        "gate_wait_s": round(gate_wait_s, 4),
        "n_writes": n_writes, "n_gated": n_gated, "fail_closed": fail_closed,
    }


# ------------------------------- aggregation ----------------------------------
def _pass(r):  # tau-bench reward is in [0,1]; 1.0 == task solved
    return r["reward"] >= 0.999


def aggregate(records, out_path):
    by_arm = defaultdict(list)
    for r in records:
        by_arm[r["arm"]].append(r)

    print("=" * 82)
    print("P6: completion A/B -- tau-bench episodes with vs without the admission gate")
    print("-" * 82)
    print(f"  {'arm':7s} {'n':>4s} {'pass@1':>10s} {'mean_rwd':>9s} "
          f"{'p50_lat':>8s} {'p95_lat':>8s} {'writes':>7s} {'gated':>6s} {'fail_closed':>12s}")
    for arm in ("nogate", "gate"):
        rs = by_arm.get(arm)
        if not rs:
            continue
        n = len(rs)
        passed = sum(1 for r in rs if _pass(r))
        mean_r = sum(r["reward"] for r in rs) / n
        lats = sorted(r["wall_s"] for r in rs)
        p50 = statistics.median(lats)
        p95 = lats[min(n - 1, int(0.95 * n))]
        writes = sum(r["n_writes"] for r in rs)
        gated = sum(r["n_gated"] for r in rs)
        fc = sum(r["fail_closed"] for r in rs)
        print(f"  {arm:7s} {n:>4d} {passed:>4d}/{n:<3d}={passed/n:>4.2f} {mean_r:>9.3f} "
              f"{p50:>7.2f}s {p95:>7.2f}s {writes:>7d} {gated:>6d} {fc:>12d}")

    A, B = by_arm.get("nogate", []), by_arm.get("gate", [])
    if A and B:
        pa = sum(1 for r in A if _pass(r)) / len(A)
        pb = sum(1 for r in B if _pass(r)) / len(B)
        ra = {r["task_index"]: r["reward"] for r in A}
        rb = {r["task_index"]: r["reward"] for r in B}
        common = sorted(set(ra) & set(rb))
        matched = sum(1 for i in common if abs(ra[i] - rb[i]) < 1e-6)
        la = statistics.median(r["wall_s"] for r in A)
        lb = statistics.median(r["wall_s"] for r in B)
        fc = sum(r["fail_closed"] for r in B)
        gwait = [r["gate_wait_s"] for r in B if r["n_gated"] > 0]
        print("-" * 82)
        print(f"  A/B  pass@1: nogate {pa:.3f}  gate {pb:.3f}  (Delta {pb - pa:+.3f}; ~0 means the gate does not break tasks)")
        print(f"       per-task reward identical on {matched}/{len(common)} shared tasks "
              f"(divergences are model nondeterminism, not the gate)")
        print(f"       median episode latency: nogate {la:.2f}s  gate {lb:.2f}s  (overhead {lb - la:+.2f}s)")
        if gwait:
            print(f"       gate wait per gated episode: median {statistics.median(gwait) * 1000:.1f} ms "
                  f"(the admission round-trips; the rest of any latency delta is model noise)")
        print(f"       FALSE POSITIVES (fail-closed on a legitimate write): {fc}  (MUST be 0)")
        if fc:
            print("       !! non-zero fail-closed -- the gate refused a legitimate effect; investigate.")

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        print(f"\n  per-episode records appended -> {out_path}")


# --------------------------------- resume -------------------------------------
def load_done(out_path):
    done = set()
    if not out_path or not Path(out_path).exists():
        return done
    with open(out_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                done.add((r["arm"], int(r["task_index"])))
            except Exception:
                pass
    return done


# ------------------------------- self-test ------------------------------------
def self_test(port):
    """Offline: stub tau-bench's user simulator, drive a scripted retail episode
    through BOTH arms against a live gate, and assert the gate arm routed and
    RELEASED the write with zero fail-closed. No API is touched."""
    repo = os.environ.get("PYTHONPATH", "").split(":")[0]
    if repo:
        sys.path.insert(0, repo)
    try:
        import tau_bench.envs.user as U
    except Exception as e:
        print(f"SELF-TEST SKIPPED: tau-bench not importable ({e}). "
              f"Set PYTHONPATH=/path/to/tau-bench to run it.")
        return 0

    class _StubUser(U.LLMUserSimulationEnv):
        def reset(self, instruction=None):
            self.messages = []
            return "STUB: " + (instruction or "")
        def step(self, content):
            return "STUB user reply"
        def get_total_cost(self):
            return 0.0
    U.LLMUserSimulationEnv = _StubUser
    from tau_bench.envs import get_env

    srv = subprocess.Popen([str(BIN), f"127.0.0.1:{port}"], stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    try:
        gate = GateClient(("127.0.0.1", port))
        recs = []
        for arm in ("nogate", "gate"):
            env = get_env("retail", user_strategy="llm", user_model="none",
                          user_provider="openai", task_split="test", task_index=0)
            rec = run_episode_ab(env, MockModel(), "mock", "mock", env.tools_info,
                                 "retail", 0, max_turns=6, temperature=0.0,
                                 gate=gate, arm=arm)
            recs.append(rec)
        gate.close()
    finally:
        srv.terminate()

    g = next(r for r in recs if r["arm"] == "gate")
    ng = next(r for r in recs if r["arm"] == "nogate")
    assert g["n_writes"] >= 1, "self-test: no consequential write seen in the scripted episode"
    assert g["n_gated"] >= 1, "self-test: gate arm did not route the write"
    assert g["fail_closed"] == 0, f"self-test: gate wrongly blocked a legitimate write ({g['fail_closed']})"
    assert ng["n_gated"] == 0, "self-test: nogate arm should not touch the gate"
    print("SELF-TEST PASS: both arms complete; the gate arm routed the write, "
          "released it on auto-approve, and fail-closed=0. Gate mechanics + loop OK.")
    aggregate(recs, None)
    return 0


# ---------------------------------- main --------------------------------------
def cmd_run(args):
    if args.self_test:
        return self_test(args.port)

    repo = os.environ.get("PYTHONPATH", "").split(":")[0]
    if repo:
        sys.path.insert(0, repo)
    from tau_bench.envs import get_env

    arms = ["nogate", "gate"] if args.arm == "both" else [args.arm]
    done = load_done(args.out)

    srv = subprocess.Popen([str(BIN), f"127.0.0.1:{args.port}"], stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    records = []
    try:
        gate = GateClient(("127.0.0.1", args.port))
        total = len(arms) * (args.end - args.start)
        completed = 0
        for arm in arms:
            for idx in range(args.start, args.end):
                if (arm, idx) in done:
                    completed += 1
                    continue
                try:
                    env = get_env(args.env, user_strategy=args.user_strategy,
                                  user_model=args.user_model, user_provider=args.provider,
                                  task_split=args.task_split, task_index=idx)
                    rec = run_episode_ab(env, complete_real, args.model, args.provider,
                                         env.tools_info, args.env, idx, args.max_turns,
                                         args.temperature, gate, arm)
                except Exception as e:  # one bad episode shouldn't sink the run
                    print(f"  [{arm} task {idx}] error: {e}", file=sys.stderr)
                    continue
                records.append(rec)
                completed += 1
                # live progress (stderr; the --out receipt stays clean)
                print(f"\r  [{completed:>{len(str(total))}}/{total}] {arm:6s} task {idx} "
                      f"reward={rec['reward']:.0f} lat={rec['wall_s']:.1f}s "
                      f"gated={rec['n_gated']} fail_closed={rec['fail_closed']}   ",
                      end="", file=sys.stderr, flush=True)
                if args.out:  # append incrementally so a crash keeps progress
                    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                    with open(args.out, "a") as fh:
                        fh.write(json.dumps(rec) + "\n")
        gate.close()
    finally:
        srv.terminate()
        print("", file=sys.stderr)

    # aggregate over the full file (records already appended above; read them all
    # so resumed runs are included in the summary).
    all_recs = []
    if args.out and Path(args.out).exists():
        for line in open(args.out):
            line = line.strip()
            if line:
                try:
                    all_recs.append(json.loads(line))
                except Exception:
                    pass
    else:
        all_recs = records
    aggregate(all_recs, None)  # print only; file already written incrementally
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=["retail", "airline"], default="retail")
    ap.add_argument("--provider", default="openai", help="openai | anthropic")
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--user-model", default="gpt-4o-mini", help="user-simulator model")
    ap.add_argument("--user-strategy", default="llm")
    ap.add_argument("--task-split", default="test")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=20)
    ap.add_argument("--arm", choices=["both", "nogate", "gate"], default="both")
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--port", type=int, default=8807)
    ap.add_argument("--out", default=None, help="JSONL receipt (resume-safe)")
    ap.add_argument("--self-test", action="store_true", help="offline mock, no API")
    args = ap.parse_args()
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())