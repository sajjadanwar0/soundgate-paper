# `scripts/` — repo-level tooling

## `mediation_lint.py` — static mediation linter
Best-effort check supporting the complete-mediation contract: it flags direct
calls to registered side-effecting callables that bypass the gate wrapper, so an
*accidental* unwrapped effect surfaces at lint time rather than at runtime.

```bash
python3 scripts/mediation_lint.py path/to/your/agent/
```

Scope (as in the paper): dynamic dispatch and third-party internals are
invisible to it — it raises the cost of *accidental* bypass, not malicious
bypass. The structural routes in `soundgate/ebpf/` close the network channel
below the application; this linter is the developer-facing layer above it.