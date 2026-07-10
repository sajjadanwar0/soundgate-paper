#!/usr/bin/env bash
# Reproduce Experiment 1: non-network channels fail-closed under seccomp
# confinement. Requires: gcc, libseccomp-dev (apt-get install -y libseccomp-dev)
#
# NOTE: evil_tool and confine intentionally exit non-zero (they report the
# leak/refusal count as their status), so we must NOT run the arms under
# `set -e` or the script aborts mid-demo. We keep -u and pipefail, drop -e
# around the arms, and capture each exit code explicitly.
set -uo pipefail
cd "$(dirname "$0")"

# The confinement source has historically shipped as cofine.c (sic); accept
# either name so a rename never silently breaks the build.
SRC=""
for c in confine.c cofine.c; do [ -f "$c" ] && SRC="$c" && break; done
if [ -z "$SRC" ]; then echo "ERROR: no confine.c/cofine.c source found" >&2; exit 2; fi

gcc -O2 -o evil_tool evil_tool.c || { echo "ERROR: evil_tool build failed" >&2; exit 2; }
gcc -O2 -o confine  "$SRC" -lseccomp || { echo "ERROR: confine build failed ($SRC)" >&2; exit 2; }
rm -f /tmp/sg_exfil.txt

# Truncate the receipt up front so a failed run can never leave stale content.
: > confine_fs.txt
{
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)  kernel: $(uname -r)  libseccomp: $(pkg-config --modversion libseccomp 2>/dev/null)  src: $SRC"
  echo ">>> ARM A -- UNCONFINED (residual):"
  ./evil_tool; A=$?
  echo ">>> ARM B -- CONFINED (seccomp; gate egress provisioned):"
  ./confine --gate-pipe ./evil_tool; B=$?
  echo "unconfined leaks: $A/3   confined leaks: $B/3"
  if [ "$A" -eq 3 ] && [ "$B" -eq 0 ]; then
    echo "VERDICT: PASS (fail-open -> fail-closed)"
  else
    echo "VERDICT: CHECK (expected A=3, B=0; got A=$A, B=$B)"
  fi
} | tee confine_fs.txt