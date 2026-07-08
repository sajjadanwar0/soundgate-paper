"""Once `import soundgate` works, this is the 30-second end-to-end smoke test.

Terminal 1:  ./target/release/soundgate 127.0.0.1:8796      # start the gate
Terminal 2:  python smoke_test.py                            # run this
"""
from soundgate import GateClient   # the PyO3 extension (or: from soundgate_client import GateClient)

g = GateClient("127.0.0.1:8796")
assert g.ping().kind == "pong"

# P1: a consequential effect is held until decided
v = g.submit("run1", "send_email", needs_approval=True)
assert v.held and v == "held_for_approval", v
assert g.decide("run1", "send_email", True).released           # approve -> release

# P3: the same identity cannot release twice
assert g.submit("run1", "send_email", needs_approval=True) == "refused_duplicate"

# P4: a cancelled run's effect is fenced
g.cancel("run2")
assert g.submit("run2", "charge_card", needs_approval=True) == "refused_cancelled"

print("OK — gate reachable, P1/P3/P4 behave correctly from Python")