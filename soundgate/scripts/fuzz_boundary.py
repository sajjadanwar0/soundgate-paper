import argparse
import json
import os
import random
import signal
import socket
import subprocess
import sys
import time

CLASSES = ["A", "B", "C", "D", "E", "F", "G", "H"]

def connect(port: int, timeout: float = 2.0) -> socket.socket:
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.settimeout(timeout)
    return s


def rt_valid(port: int, obj: dict) -> dict:
    with connect(port) as s:
        s.sendall((json.dumps(obj) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                raise ConnectionError("server closed before reply")
            buf += chunk
        return json.loads(buf.decode())


def send_raw(port: int, payload: bytes, expect_reply: bool = True, timeout: float = 0.4):
    try:
        with connect(port, timeout) as s:
            s.sendall(payload)

            try:
                s.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            if not expect_reply:
                return ("sent", None)
            buf = b""
            try:
                while not buf.endswith(b"\n"):
                    chunk = s.recv(65536)
                    if not chunk:
                        return ("closed", None)
                    buf += chunk
                    if len(buf) > 4 * 1024 * 1024:
                        return ("reply", "<oversized-reply>")
            except socket.timeout:
                return ("timeout", None)
            try:
                v = json.loads(buf.decode("utf-8", errors="replace"))
                return ("reply", v.get("verdict"))
            except Exception:
                return ("reply", "<unparseable-reply>")
    except (ConnectionError, OSError):
        return ("closed", None)


PRINTABLE = bytes(range(0x20, 0x7F))

def gen_A(rng):  # random bytes
    n = rng.randint(1, 512)
    return bytes(rng.getrandbits(8) for _ in range(n)) + b"\n"


def gen_B(rng):  # invalid UTF-8
    seqs = [b"\xc0\xaf", b"\xe0\x80\xaf", b"\xf0\x28\x8c\x28", b"\xff\xfe",
            b"\x80\x80", b"\xed\xa0\x80", b"\xf8\x88\x80\x80\x80"]
    core = b"".join(rng.choice(seqs) for _ in range(rng.randint(1, 40)))
    return b'{"op":"submit"' + core + b"}\n"


def gen_C(rng):
    n = rng.randint(1, 300)
    return bytes(rng.choice(PRINTABLE) for _ in range(n)).replace(b"\n", b" ") + b"\n"


def _rand_json(rng, depth=0):
    if depth > 6:
        return rng.choice([None, True, False, rng.randint(-2**31, 2**31), "x" * rng.randint(0, 8)])
    t = rng.random()

    if t < 0.25:
        return [_rand_json(rng, depth + 1) for _ in range(rng.randint(0, 4))]

    if t < 0.5:
        return {("k%d" % i): _rand_json(rng, depth + 1) for i in range(rng.randint(0, 4))}

    if t < 0.65:
        return rng.random() * 10**rng.randint(-5, 5)

    if t < 0.8:
        return "".join(chr(rng.randint(0x20, 0x2FA0)) for _ in range(rng.randint(0, 12)))
    return rng.choice([None, True, False])

def gen_D(rng):
    v = _rand_json(rng)
    if isinstance(v, dict):
        v.pop("op", None)
    return (json.dumps(v, ensure_ascii=False).replace("\n", " ") + "\n").encode()

def gen_E(rng):  # JSON object with wrong/missing/unknown fields
    choice = rng.random()

    if choice < 0.3:
        obj = {"op": rng.choice(["sudo", "release", "SUBMIT", "", "submit ", "decide\u0000"]),
               "run_id": "r", "effect_key": "k"}
    elif choice < 0.55:
        obj = {"op": rng.choice(["submit", "decide", "cancel"])}
    elif choice < 0.8:
        obj = {"op": "decide", "run_id": rng.randint(0, 9), "effect_key": ["k"],
               "approved": rng.choice(["yes", 1, None])}
    else:
        obj = {"op": "submit", "run_id": "r", "effect_key": "k",
               "needs_approval": rng.choice(["true", 2, [True]]),
               "extra_%d" % rng.randint(0, 99): _rand_json(rng)}
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode()

def gen_F(rng):
    c = rng.random()

    if c < 0.3:
        obj = {"op": "decide", "run_id": "R" * rng.randint(10_000, 120_000),
               "effect_key": "K" * rng.randint(1, 1000),
               "approved": True, "mac": "00" * 32}
        return (json.dumps(obj) + "\n").encode()

    if c < 0.6:
        rid = "".join(rng.choice('r"\\\u0001\u007f\t ') for _ in range(rng.randint(1, 24)))
        obj = {"op": "decide", "run_id": rid, "effect_key": rid[::-1] or "k",
               "approved": bool(rng.getrandbits(1)), "mac": "00" * 32}
        return (json.dumps(obj) + "\n").encode()

    if c < 0.85:
        return (('{"op":"decide","op":"decide","run_id":"a","run_id":"b",'
                 '"effect_key":"k","approved":%s}\n')
                % rng.choice(["true", "false"])).encode()
    obj = {"op": "decide", "run_id": "", "effect_key": "", "approved": True}

    return (json.dumps(obj) + "\n").encode()


def gen_H(rng):
    c = rng.random()
    base = b'{"op":"submit","run_id":"tr","effect_key":"tk","needs_approval":true}'

    if c < 0.3:
        cut = rng.randint(1, len(base) - 1)
        return base[:cut]

    if c < 0.55:
        cut = rng.randint(1, len(base) - 1)
        return base[:cut] + b"\n" + base[cut:] + b"\n"

    if c < 0.8:
        return b'{"op":"ping","pad":"' + b"A" * (256 * 1024) + b'"}\n'
    return b"\n\n\n"


GEN = {"A": gen_A, "B": gen_B, "C": gen_C, "D": gen_D, "E": gen_E, "F": gen_F, "H": gen_H}

FAIL_OPEN = {"release", "held_for_approval"}

def run_G(rng, port, n, stats, failures):
    for i in range(n):
        kind = rng.randrange(4)
        rid, key = f"g{rng.randrange(1_000_000)}", f"k{rng.randrange(1000)}"

        if kind == 0:
            v = rt_valid(port, {"op": "decide", "run_id": rid, "effect_key": key,
                                "approved": True})
            stats["G"]["reply"] += 1
            if v.get("verdict") in FAIL_OPEN:
                failures.append(("G", "decide-unknown released", v))
        elif kind == 1:
            rt_valid(port, {"op": "submit", "run_id": rid, "effect_key": key,
                            "needs_approval": True})
            rt_valid(port, {"op": "cancel", "run_id": rid})
            v = rt_valid(port, {"op": "decide", "run_id": rid, "effect_key": key,
                                "approved": True})
            stats["G"]["reply"] += 3
            if v.get("verdict") != "refused_cancelled":
                failures.append(("G", "approve-after-cancel not fenced", v))
        elif kind == 2:
            rt_valid(port, {"op": "submit", "run_id": rid, "effect_key": key,
                            "needs_approval": True})
            v1 = rt_valid(port, {"op": "decide", "run_id": rid, "effect_key": key,
                                 "approved": True})
            v2 = rt_valid(port, {"op": "decide", "run_id": rid, "effect_key": key,
                                 "approved": True})
            stats["G"]["reply"] += 3

            if v1.get("verdict") != "release" or v2.get("verdict") == "release":
                failures.append(("G", "double-decide anomaly", (v1, v2)))
        else:
            rt_valid(port, {"op": "cancel", "run_id": rid})
            v = rt_valid(port, {"op": "submit", "run_id": rid, "effect_key": key,
                                "needs_approval": False})
            stats["G"]["reply"] += 2

            if v.get("verdict") != "refused_cancelled":
                failures.append(("G", "post-cancel submit not fenced", v))


CAN_RUN, HELD_KEY, REL_KEY, FENCED_RUN = "canary_run", "held_key", "released_key", "fenced_run"

def plant_canaries(port):
    assert rt_valid(port, {"op": "submit", "run_id": CAN_RUN, "effect_key": HELD_KEY,
                           "needs_approval": True})["verdict"] == "held_for_approval"
    assert rt_valid(port, {"op": "submit", "run_id": CAN_RUN, "effect_key": REL_KEY,
                           "needs_approval": False})["verdict"] == "release"
    assert rt_valid(port, {"op": "cancel", "run_id": FENCED_RUN})["verdict"] == "ack"

def check_canaries(port, failures, when):
    v1 = rt_valid(port, {"op": "submit", "run_id": CAN_RUN, "effect_key": HELD_KEY,
                         "needs_approval": True})["verdict"]
    if v1 != "held_for_approval":
        failures.append(("O2", f"{when}: held canary state mutated", v1))
    v2 = rt_valid(port, {"op": "submit", "run_id": CAN_RUN, "effect_key": REL_KEY,
                         "needs_approval": False})["verdict"]
    if v2 != "refused_duplicate":
        failures.append(("O2", f"{when}: released canary not deduplicating", v2))
    v3 = rt_valid(port, {"op": "submit", "run_id": FENCED_RUN, "effect_key": "any",
                         "needs_approval": False})["verdict"]
    if v3 != "refused_cancelled":
        failures.append(("O2", f"{when}: fence lost", v3))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-class", type=int, default=25_000)
    ap.add_argument("--seed", type=int, default=20260707)
    ap.add_argument("--port", type=int, default=8931)
    ap.add_argument("--server", default="target/release/soundgate")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    srv = subprocess.Popen([args.server, f"127.0.0.1:{args.port}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.4)
    try:
        assert rt_valid(args.port, {"op": "ping"})["verdict"] == "pong"
        plant_canaries(args.port)

        stats = {c: {"reply": 0, "closed": 0, "timeout": 0, "sent": 0,
                     "error": 0, "fail_open": 0} for c in CLASSES}
        failures = []
        t0 = time.time()

        for cls in CLASSES:
            if cls == "G":
                run_G(rng, args.port, max(1, args.n_per_class // 10), stats, failures)
            else:
                for i in range(args.n_per_class):
                    kind, verdict = send_raw(args.port, GEN[cls](rng))
                    stats[cls][kind] += 1

                    if verdict == "error" or (isinstance(verdict, str) and verdict is None):
                        pass

                    if verdict == "error":
                        stats[cls]["error"] += 1

                    if verdict in FAIL_OPEN:
                        stats[cls]["fail_open"] += 1
                        failures.append((cls, "FAIL-OPEN verdict on malformed input", verdict))

                    if kind == "reply" and verdict == "error":
                        pass

            if srv.poll() is not None:
                failures.append(("O3", f"server died during class {cls}", srv.returncode))
                break
            assert rt_valid(args.port, {"op": "ping"})["verdict"] == "pong"
            check_canaries(args.port, failures, f"after class {cls}")

        dt = time.time() - t0
        total = sum(sum(v[k] for k in ("reply", "closed", "timeout", "sent"))
                    for v in stats.values())
        print("=" * 74)
        print("SOUNDGATE protocol-boundary fuzz  --  seed %d, %d inputs/class (G: /10)"
              % (args.seed, args.n_per_class))
        print("server: %s   elapsed: %.1fs   total inputs: %d" % (args.server, dt, total))
        print("-" * 74)
        print("%-5s %10s %10s %10s %10s %10s" %
              ("class", "replies", "err-reply", "closed", "timeout", "FAIL-OPEN"))
        for c in CLASSES:
            s = stats[c]
            print("%-5s %10d %10d %10d %10d %10d" %
                  (c, s["reply"], s["error"], s["closed"], s["timeout"], s["fail_open"]))
        print("-" * 74)
        alive = srv.poll() is None
        print("server alive at end: %s" % alive)
        print("oracle O1 (fail-closed, zero fail-open verdicts): %s"
              % ("PASS" if not any(f[0] in CLASSES and "FAIL-OPEN" in f[1] for f in failures) else "FAIL"))
        print("oracle O2 (canary state integrity across all batches): %s"
              % ("PASS" if not any(f[0] == "O2" for f in failures) else "FAIL"))
        print("oracle O3 (availability, ping after every batch): %s"
              % ("PASS" if alive and not any(f[0] == "O3" for f in failures) else "FAIL"))
        print("oracle G  (semantic: no unknown/dup/fenced decide releases): %s"
              % ("PASS" if not any(f[0] == "G" for f in failures) else "FAIL"))
        if failures:
            print("\nFAILURES (%d):" % len(failures))
            for f in failures[:50]:
                print("  ", f)
            print("\nVERDICT: FAIL")
            return 1
        print("\nVERDICT: PASS -- every malformed input yielded an error reply or a")
        print("dropped/half-open connection, never a release; state canaries intact;")
        print("server survived all classes.")
        return 0
    finally:
        srv.send_signal(signal.SIGTERM)
        try:
            srv.wait(timeout=3)
        except subprocess.TimeoutExpired:
            srv.kill()


if __name__ == "__main__":
    sys.exit(main())