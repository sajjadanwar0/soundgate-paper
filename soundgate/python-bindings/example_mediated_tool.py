"""How a Python agent framework wraps a side-effecting tool with the gate.

Framework-agnostic: the wrapper submits the effect for admission and performs
it only on `release`. Works identically whether `GateClient` comes from the
PyO3 extension (`from soundgate import GateClient`) or the pure-Python client
(`from soundgate_client import GateClient`).
"""

from soundgate_client import GateClient  # or: from soundgate import GateClient


def mediated(gate: GateClient, run_id: str, effect_key: str, do_effect, needs_approval=True):
    """Admit `do_effect` through the gate. Returns the effect's result on
    release, or a sentinel string describing the refusal/hold."""
    v = gate.submit(run_id, effect_key, needs_approval=needs_approval)
    if v.released:
        return do_effect()
    # held_for_approval / refused_*: the effect must NOT run.
    return f"[gate: {v}] effect not performed"


# --- example: a LangGraph-style tool ---------------------------------------
# @tool
# def send_email(to: str, body: str, *, run_id: str, gate: GateClient):
#     return mediated(
#         gate, run_id, effect_key=f"send_email:{to}",
#         do_effect=lambda: _really_send(to, body),
#         needs_approval=True,
#     )
#
# A human approves out-of-band via gate.decide(run_id, "send_email:bob@x.com", True).