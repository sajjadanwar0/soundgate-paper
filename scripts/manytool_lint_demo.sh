#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
EV=../soundgate/evidence; mkdir -p "$EV"; OUT="$EV/mediation_lint_manytool.txt"
EFFECTS=$(python3 -c "import sys; sys.path.insert(0,'manytool_fixture');
from registry import EFFECTS; print(','.join(EFFECTS))")

FINDINGS=$(python3 mediation_lint.py --wrapper gate_effect --effects "$EFFECTS" manytool_fixture/ || true)

python3 - "$OUT" <<PY
import pathlib, re, sys
out = pathlib.Path(sys.argv[1])
findings = """$FINDINGS""".strip().splitlines()
fix = pathlib.Path("manytool_fixture")
static_marks, dyn_marks = {}, {}
nfiles = nlines = 0
for f in sorted(fix.glob("*.py")):
    nfiles += 1
    for i, line in enumerate(f.read_text().splitlines(), 1):
        nlines += 1
        if "SEEDED-STATIC-BYPASS" in line: static_marks[(f.name, i)] = line.strip()
        if "SEEDED-DYNAMIC-BYPASS" in line: dyn_marks[(f.name, i)] = line.strip()
flagged = set()
for line in findings:
    m = re.match(r"(?:.*/)?([^/:]+):(\d+):", line)
    if m: flagged.add((m.group(1), int(m.group(2))))
static_hit = flagged & set(static_marks)
dyn_hit = flagged & set(dyn_marks)
unexpected = flagged - set(static_marks) - set(dyn_marks)
n_eff = len(open("manytool_fixture/registry.py").read().split("',"))
ok = (len(static_hit) == len(static_marks) == 8 and not dyn_hit
      and len(dyn_marks) == 4 and not unexpected)
with out.open("w") as w:
    w.write("# mediation linter at deployment scale; synthetic many-tool fixture\n")
    w.write(f"# fixture: 60 effect callables across {nfiles} modules, {nlines} lines; wrapper: gate_effect\n")
    w.write(f"# seeded bypasses: {len(static_marks)} static (bare + attribute call), {len(dyn_marks)} dynamic (getattr, dict dispatch, alias, closure alias)\n")
    w.write("# linter findings:\n")
    for line in findings: w.write(f"#   {line}\n")
    w.write(f"# direct-call bypasses flagged: {len(static_hit)}/{len(static_marks)}\n")
    w.write(f"# dynamic-dispatch bypasses flagged: {len(dyn_hit)}/{len(dyn_marks)} (stated blindness, measured)\n")
    w.write(f"# false positives on legitimate wrapped call sites: {len(unexpected)}\n")
    w.write(f"# RESULT: {'PASS' if ok else 'FAIL'}\n")
print(out.read_text())
sys.exit(0 if ok else 1)
PY
