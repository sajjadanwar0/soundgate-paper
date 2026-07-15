from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import shutil
import sys
import tempfile
from pathlib import Path
import soundgate
import traceback

try:
    _addr = os.environ.get("SOUNDGATE_ADDR")
    GATE = soundgate.GateClient(_addr) if _addr else soundgate.Gate()
    GATE_MODE = f"external {_addr}" if _addr else "in-process Gate"
except Exception as e:
    GATE = None
    GATE_MODE = f"unavailable ({e!r}); filesystem arm only"

NR_landlock_create_ruleset = 444
NR_landlock_add_rule = 445
NR_landlock_restrict_self = 446
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
LANDLOCK_RULE_PATH_BENEATH = 1
LANDLOCK_CREATE_RULESET_VERSION = 1 << 0

PR_SET_NO_NEW_PRIVS = 38

libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
libc.syscall.restype = ctypes.c_long

class landlock_ruleset_attr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64),
                ("handled_access_net", ctypes.c_uint64)]

class landlock_path_beneath_attr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64),
                ("parent_fd", ctypes.c_int32)]


def _syscall(nr: int, *args) -> int:
    ctypes.set_errno(0)
    res = libc.syscall(ctypes.c_long(nr), *args)

    if res < 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))

    return res


def landlock_abi() -> int:
    try:
        return _syscall(NR_landlock_create_ruleset, None, ctypes.c_size_t(0),
                        ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION))
    except OSError:
        return 0

HANDLED = LANDLOCK_ACCESS_FS_WRITE_FILE


def restrict_to_workdir(workdir: str, trace=lambda m: None) -> None:
    trace(f"    sizeof(ruleset_attr)={ctypes.sizeof(landlock_ruleset_attr)} "
          f"sizeof(path_beneath_attr)={ctypes.sizeof(landlock_path_beneath_attr)}"
          f" (expect 16 and 12)")
    attr = landlock_ruleset_attr(handled_access_fs=HANDLED,
                                 handled_access_net=0)
    rs_fd = _syscall(NR_landlock_create_ruleset,
                     ctypes.cast(ctypes.byref(attr), ctypes.c_void_p),
                     ctypes.c_size_t(ctypes.sizeof(attr)),
                     ctypes.c_uint32(0))
    trace(f"    create_ruleset -> fd={rs_fd}")
    dir_fd = os.open(workdir, os.O_PATH | os.O_DIRECTORY)

    try:
        rule = landlock_path_beneath_attr(allowed_access=HANDLED,
                                          parent_fd=dir_fd)
        ar = _syscall(NR_landlock_add_rule,
                      ctypes.c_int(rs_fd),
                      ctypes.c_uint32(LANDLOCK_RULE_PATH_BENEATH),
                      ctypes.cast(ctypes.byref(rule), ctypes.c_void_p),
                      ctypes.c_uint32(0))
        trace(f"    add_rule(PATH_BENEATH, workdir_fd={dir_fd}) -> {ar}")
        nnp_before = libc.prctl(ctypes.c_int(39), 0, 0, 0, 0)

        set_ret = libc.prctl(ctypes.c_int(PR_SET_NO_NEW_PRIVS),
                             ctypes.c_ulong(1), ctypes.c_ulong(0),
                             ctypes.c_ulong(0), ctypes.c_ulong(0))
        nnp_after = libc.prctl(ctypes.c_int(39), 0, 0, 0, 0)

        trace(f"    no_new_privs before={nnp_before} set_ret={set_ret} "
              f"after={nnp_after} (after must be 1)")

        if set_ret != 0 or nnp_after != 1:
            raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS) failed")
        rr = _syscall(NR_landlock_restrict_self, ctypes.c_int(rs_fd),
                      ctypes.c_uint32(0))
        trace(f"    restrict_self -> {rr} (0 = ruleset now enforced)")
    finally:
        os.close(dir_fd)
        os.close(rs_fd)

def _try_write(path: str, data: str) -> tuple[bool, str]:
    try:
        fd = os.open(path, os.O_WRONLY)
        try:
            os.write(fd, data.encode())
        finally:
            os.close(fd)
        return True, "committed"
    except PermissionError as e:
        return False, f"refused (EACCES/errno {e.errno})"
    except OSError as e:
        return False, f"refused (errno {e.errno})"

def mediated_write(run_id: str, key: str, path: str, data: str) -> tuple[bool, str]:
    if GATE is None:
        ok, detail = _try_write(path, data)
        return ok, f"(no gate) {detail}"
    v = GATE.submit(run_id, key, False)

    if getattr(v, "released", str(v) == "release"):
        ok, detail = _try_write(path, data)
        return ok, f"released -> {detail}"

    return False, f"gate verdict {v}; not written"


def landlock_selftest() -> tuple[bool, str]:
    r, w = os.pipe()
    pid = os.fork()

    if pid == 0:
        os.close(r)
        try:
            probe = tempfile.NamedTemporaryFile(
                prefix=".ll_selftest_", dir=os.path.dirname(
                    os.path.abspath(__file__)), delete=False)
            probe.write(b"seed")
            probe.close()

            attr = landlock_ruleset_attr(handled_access_fs=HANDLED,
                                         handled_access_net=0)
            rs = _syscall(NR_landlock_create_ruleset,
                          ctypes.cast(ctypes.byref(attr), ctypes.c_void_p),
                          ctypes.c_size_t(ctypes.sizeof(attr)),
                          ctypes.c_uint32(0))
            libc.prctl(ctypes.c_int(PR_SET_NO_NEW_PRIVS), ctypes.c_ulong(1),
                       ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0))
            _syscall(NR_landlock_restrict_self, ctypes.c_int(rs),
                     ctypes.c_uint32(0))
            os.close(rs)

            try:
                fd = os.open(probe.name, os.O_WRONLY)
                os.close(fd)
                os.write(w, b"ALLOWED")
            except PermissionError:
                os.write(w, b"DENIED")
            os.unlink(probe.name)
        except BaseException as e:
            os.write(w, f"ERROR:{e!r}".encode()[:200])
        os.close(w)
        os._exit(0)
    os.close(w)

    result = os.read(r, 256).decode(errors="replace")
    os.close(r)
    os.waitpid(pid, 0)

    return (result == "DENIED", result)

def child(private_dir: str, private_effect: str, shared_leak: str,
          outside_leak: str, shared_readable: str) -> int:
    def out(msg: str) -> None:
        print(msg, flush=True)

    try:
        abi = landlock_abi()
        if abi >= 1:
            enforcing, st = landlock_selftest()
            out(f"  ENFORCEMENT SELF-TEST (handle write, grant nothing "
                f"-> write must be denied): {st} "
                f"-> {'ENFORCING' if enforcing else 'NOT ENFORCING'}")
            out("  [syscall trace]")
            restrict_to_workdir(private_dir, trace=out)
            enforced = True
        else:
            enforced = False

        out(f"  Landlock ABI: {abi} "
            f"({'ENFORCED' if enforced else 'UNAVAILABLE'})")
        out(f"  handled_access_fs=0x{HANDLED:x} (WRITE_FILE); "
            f"granted beneath workdir only")
        out(f"  gate mode: {GATE_MODE}")

        probes = []

        ok_w, d_w = mediated_write("landlock-run", "write_workdir",
                                   private_effect, "legit mediated effect\n")
        probes.append(("W1 mediated write -> workdir (expect ALLOW)",
                       ok_w, True, d_w))
        ok_s, d_s = _try_write(shared_leak, "leak another proc reads\n")
        probes.append(("W2 unmediated write -> shared observed path "
                       "(expect DENY)", ok_s, False, d_s))
        ok_o, d_o = _try_write(outside_leak, "write outside any grant\n")
        probes.append(("W3 unmediated write -> outside workdir "
                       "(expect DENY: proves restriction active)",
                       ok_o, False, d_o))

        try:
            with open(shared_readable) as f:
                f.read()
            ok_r, d_r = True, "read ok"
        except OSError as e:
            ok_r, d_r = False, f"read refused (errno {e.errno})"
        probes.append(("R1 read -> shared path (expect ALLOW: reads "
                       "ungoverned)", ok_r, True, d_r))

        all_ok = True

        for name, got, want, detail in probes:
            passed = (got == want)
            all_ok &= passed
            verdict = "PASS" if passed else "FAIL"
            got_s = "allowed" if got else "denied"
            out(f"  {name:<58} -> {verdict}  ({got_s})  {detail}")

        if not enforced:
            out("\n  UNAVAILABLE: kernel lacks Landlock "
                "(CONFIG_SECURITY_LANDLOCK); run on a >= 5.13 kernel.")
            sys.stdout.flush()
            return 2
        code = 0 if all_ok else 1
    except BaseException as e:
        out(f"  CHILD ERROR: {e!r}")
        traceback.print_exc()
        code = 3
    sys.stdout.flush()

    return code

def main() -> int:
    print("== LANDLOCK-CONFINE: path-granular filesystem mediation ==")
    print(f"  python {sys.version.split()[0]}; kernel {os.uname().release}")
    base = os.path.dirname(os.path.abspath(__file__))
    root = tempfile.mkdtemp(prefix=".landlock_demo_", dir=base)
    outside = tempfile.mkdtemp(prefix=".landlock_outside_", dir=base)
    print(f"  filesystem under test: {base}")
    private_dir = os.path.join(root, "workdir")
    shared_dir = os.path.join(root, "shared")

    os.makedirs(private_dir)
    os.makedirs(shared_dir)

    private_effect = os.path.join(private_dir, "mediated_effect.txt")
    shared_leak = os.path.join(shared_dir, "unmediated_leak.txt")
    shared_readable = os.path.join(shared_dir, "readable.txt")
    outside_leak = os.path.join(outside, "outside_leak.txt")

    for p in (private_effect, shared_leak, shared_readable, outside_leak):
        Path(p).write_text("seed\n")
    try:
        pid = os.fork()

        if pid == 0:
            os._exit(child(private_dir, private_effect, shared_leak,
                           outside_leak, shared_readable))
        _, status = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(status)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)

    verdict = {0: "TIGHTENED (workdir write allowed; shared and outside writes "
                  "refused by kernel; reads ungoverned)",
               1: "FAILED (a probe did not match expectation; see matrix)",
               2: "UNAVAILABLE (no Landlock on this kernel)",
               3: "ERROR (child raised; see traceback above)"}
    print(f"\nLANDLOCK VERDICT: {verdict.get(code, code)}")

    return code

if __name__ == "__main__":
    raise SystemExit(main())