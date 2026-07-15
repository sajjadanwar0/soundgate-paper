from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import socket
from typing import Optional, Tuple


def decision_tag(secret: bytes, run_id: str, effect_key: str, approved: bool) -> str:
    """HMAC-SHA256(secret, "run_id\\neffect_key\\n{1|0}") as lowercase hex.

    Matches soundgate/src/hmac.rs::decision_tag exactly.
    """
    msg = f"{run_id}\n{effect_key}\n{'1' if approved else '0'}".encode("utf-8")
    return _hmac.new(secret, msg, hashlib.sha256).hexdigest()


class Verdict:
    """A gate verdict. `v.released` / `v.held` / `v.refused`, and `v == "release"`."""

    __slots__ = ("kind",)

    def __init__(self, kind: str) -> None:
        self.kind = kind

    @property
    def released(self) -> bool:
        return self.kind == "release"

    @property
    def held(self) -> bool:
        return self.kind == "held_for_approval"

    @property
    def refused(self) -> bool:
        return self.kind.startswith("refused_")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.kind == other
        if isinstance(other, Verdict):
            return self.kind == other.kind
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.kind)

    def __str__(self) -> str:
        return self.kind

    def __repr__(self) -> str:
        return f"Verdict('{self.kind}')"


class GateError(RuntimeError):
    pass


class GateClient:
    def __init__(
            self,
            addr: Tuple[str, int] = ("127.0.0.1", 8796),
            secret: Optional[bytes] = None,
            timeout: Optional[float] = 5.0,
    ) -> None:
        self._secret = secret
        self._sock = socket.create_connection(addr, timeout=timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._rf = self._sock.makefile("r")

    def _roundtrip(self, req: dict) -> Verdict:
        line = json.dumps(req, separators=(",", ":")) + "\n"
        self._sock.sendall(line.encode("utf-8"))
        resp = self._rf.readline()
        if not resp:
            raise GateError("gate closed the connection")
        obj = json.loads(resp)
        verdict = obj.get("verdict")
        if verdict == "error":
            raise GateError(f"gate error: {obj.get('message', '?')}")
        if verdict is None:
            raise GateError(f"gate reply missing verdict: {resp!r}")
        return Verdict(verdict)

    def submit(self, run_id: str, effect_key: str, needs_approval: bool = False) -> Verdict:
        return self._roundtrip(
            {
                "op": "submit",
                "run_id": run_id,
                "effect_key": effect_key,
                "needs_approval": needs_approval,
            }
        )

    def decide(self, run_id: str, effect_key: str, approved: bool) -> Verdict:
        req = {
            "op": "decide",
            "run_id": run_id,
            "effect_key": effect_key,
            "approved": approved,
        }
        if self._secret is not None:
            req["mac"] = decision_tag(self._secret, run_id, effect_key, approved)
        return self._roundtrip(req)

    def cancel(self, run_id: str) -> Verdict:
        return self._roundtrip({"op": "cancel", "run_id": run_id})

    def ping(self) -> Verdict:
        return self._roundtrip({"op": "ping"})

    def close(self) -> None:
        try:
            self._rf.close()
        finally:
            self._sock.close()

    def __enter__(self) -> "GateClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()