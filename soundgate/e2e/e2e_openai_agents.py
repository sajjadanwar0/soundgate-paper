"""E-E2E-D: soundgate wired into a REAL OpenAI Agents SDK run (keyless).

Completes the four-execution-model repair set: FW-A Pregel/superstep, FW-B
event bus, FW-C message-passing fan-out, and here FW-D's parallel tool calls
within a single model turn (openai-agents 0.17.7) -- through the same
~20-line wrapper. The model is the probe suite's scripted stub (implements
the SDK's ``Model`` interface, zero network), so the run exercises the SDK's
real agent loop, interruption/approval machinery, and to_thread tool path.

Scenarios mirror FW-D's measured violation axes (probe transcript:
probes/results/openai_agents.txt):
  A. SIBLING LEAK + REJECT-AFTER-EFFECT REPAIRED: the stub emits, in one
     assistant turn, an approval-gated charge_card and an ungated effectful
     send_email (the leak-triggering plan shape). send_email is mediated ->
     HELD while the run pauses with result.interruptions; the human rejects
     the charge AND the held sibling -> ZERO effects executed. (Unmediated,
     the probe shows send_email's effect landing before any decision.)
  C. CANCELLATION ZOMBIE FENCED: a sync tool on the SDK's default to_thread
     path outlives task.cancel() (the probe shows its effect landing after
     the caller observes cancellation); the operator's cancel fences the run
     at the gate, so the zombie's late submission is refused_cancelled ->
     zero post-cancel effects.
Replay is not demonstrated because FW-D is natively CLEAN on that axis
(turn results cached in the resume state; probe replay 1->1), and the native
per-tool timeout is clean (async) or refused at construction (sync) -- there
is nothing to repair on those axes.

Run (uses the probes venv for openai-agents==0.17.7; gate built):
  cd soundgate && cargo build --release
  ../probes/.venv/bin/python e2e/e2e_openai_agents.py
"""
import asyncio
import json
import socket
import subprocess
import threading
import time
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

from agents import Agent, RunConfig, Runner, function_tool  # noqa: E402
from agents.items import ModelResponse  # noqa: E402
from agents.models.interface import Model  # noqa: E402
from agents.usage import Usage  # noqa: E402
from openai.types.responses import (  # noqa: E402
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

ADDR = ("127.0.0.1", 8809)
BIN = Path(__file__).resolve().parents[1] / "target" / "release" / "soundgate"
RUN_CONFIG = RunConfig(tracing_disabled=True)  # keyless: no trace export


# ---------------------------------------------------------------- gate shim
class GateClient:
    """~20-line mediation wrapper: submit; perform the effect ONLY on release."""

    def __init__(self, addr=ADDR):
        self.sock = socket.create_connection(addr, timeout=5.0)
        self.rf = self.sock.makefile("r")
        self.lock = threading.Lock()

    def _call(self, req: dict) -> str:
        with self.lock:
            self.sock.sendall((json.dumps(req) + "\n").encode())
            return json.loads(self.rf.readline())["verdict"]

    def mediated_effect(self, run_id, effect_key, do_effect, needs_approval):
        v = self._call({"op": "submit", "run_id": run_id,
                        "effect_key": effect_key,
                        "needs_approval": needs_approval})
        if v == "release":
            do_effect()
        return v

    def decide(self, run_id, effect_key, approved):
        return self._call({"op": "decide", "run_id": run_id,
                           "effect_key": effect_key, "approved": approved})

    def cancel(self, run_id):
        return self._call({"op": "cancel", "run_id": run_id})


EFFECTS = []             # the world: what actually executed
SIBLING_VERDICT = []     # verdict seen inside the mediated sibling tool
gate = None              # set in main()


# ----------------------------------------------------- scripted model stub
def _tool_call(name: str, call_id: str) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=f"fc_{call_id}", call_id=call_id, name=name,
        arguments=json.dumps({}), type="function_call", status="completed",
    )


def _final_message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_final", role="assistant", status="completed", type="message",
        content=[ResponseOutputText(annotations=[], text=text,
                                    type="output_text")],
    )


class ScriptedModel(Model):
    """Stateless scripted model: emits `plan` on a fresh turn, a final
    message once any tool output is present (same stub as the probes)."""

    def __init__(self, plan):
        self._plan = plan

    async def get_response(  # type: ignore[override]
            self, system_instructions, input, model_settings, tools,
            output_schema, handoffs, tracing, *, previous_response_id=None,
            conversation_id=None, prompt=None, **kwargs: Any,
    ) -> ModelResponse:
        has_tool_output = isinstance(input, list) and any(
            isinstance(item, dict) and item.get("type") == "function_call_output"
            for item in input
        )
        output = ([_final_message("done")] if has_tool_output
                  else [_tool_call(n, c) for n, c in self._plan])
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    def stream_response(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError("non-streaming runs only")


# ------------------------------------------------- Scenario A: sibling leak
@function_tool(needs_approval=True)
def charge_card() -> str:
    """Charge the customer's card (irreversible)."""
    EFFECTS.append("charge_card")
    return "charged"


@function_tool
def send_email() -> str:
    """Send a notification email (irreversible)."""
    v = gate.mediated_effect("runA", "send_email",
                             lambda: EFFECTS.append("send_email"),
                             needs_approval=True)
    SIBLING_VERDICT.append(v)
    return f"gate:{v}"


async def scenario_a() -> bool:
    EFFECTS.clear()
    SIBLING_VERDICT.clear()
    model = ScriptedModel(plan=[("charge_card", "call_1"),
                                ("send_email", "call_2")])
    agent = Agent(name="e2e", model=model, tools=[charge_card, send_email])

    result = await Runner.run(agent, "do the task", run_config=RUN_CONFIG)
    paused = len(result.interruptions) > 0
    effects_during_pause = len(EFFECTS)
    # HUMAN REJECTS the gated tool AND the held sibling:
    d = gate.decide("runA", "send_email", approved=False)
    if paused:
        state = result.to_state()
        for item in result.interruptions:
            state.reject(item, rejection_message="rejected by human")
        await Runner.run(agent, state, run_config=RUN_CONFIG)
    ok = (paused
          and effects_during_pause == 0
          and SIBLING_VERDICT == ["held_for_approval"]
          and d == "refused_rejected"
          and len(EFFECTS) == 0)
    print(f"A sibling-leak repaired   : paused={paused} "
          f"sibling={SIBLING_VERDICT[0] if SIBLING_VERDICT else '?'} "
          f"effects_during_pause={effects_during_pause} reject={d} "
          f"effects_total={len(EFFECTS)} "
          f"-> {'HELD+REFUSED (repaired)' if ok else 'LEAK'}")
    return ok


# -------------------------------------------- Scenario C: cancellation zombie
@function_tool
def slow_webhook() -> str:
    """Blocking side-effect tool (runs on the SDK's default to_thread path)."""
    time.sleep(0.8)  # outlives the cancellation below
    gate.mediated_effect("runC", "post_webhook",
                         lambda: EFFECTS.append("post_webhook"),
                         needs_approval=False)
    return "ok"


async def scenario_c() -> bool:
    EFFECTS.clear()
    model = ScriptedModel(plan=[("slow_webhook", "call_1")])
    agent = Agent(name="e2e", model=model, tools=[slow_webhook])

    task = asyncio.create_task(Runner.run(agent, "go", run_config=RUN_CONFIG))
    await asyncio.sleep(0.25)
    gate.cancel("runC")            # the operator's stop fences the run...
    task.cancel()                  # ...alongside the host-level cancel
    cancelled_seen = False
    try:
        await task
    except asyncio.CancelledError:
        cancelled_seen = True
    except Exception:
        pass
    await asyncio.sleep(1.2)       # zombie thread wakes, submits, is fenced
    ok = cancelled_seen and len([e for e in EFFECTS if e == "post_webhook"]) == 0
    print(f"C zombie fenced           : cancelled_seen={cancelled_seen} "
          f"zombie_effect_executed={len(EFFECTS) != 0} "
          f"effects_total={len(EFFECTS)} "
          f"-> {'FENCED (repaired)' if ok else 'ORPHANED'}")
    return ok


async def main():
    global gate
    srv = subprocess.Popen([str(BIN), f"{ADDR[0]}:{ADDR[1]}"],
                           stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    try:
        gate = GateClient()
        a = await scenario_a()
        c = await scenario_c()
        n = int(a) + int(c)
        print(f"\nE-E2E-D (real openai-agents==0.17.7, scripted model): {n}/2 "
              f"violation classes repaired in situ (replay and native timeout "
              f"are natively clean/refused on FW-D)")
        return 0 if n == 2 else 1
    finally:
        srv.terminate()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))