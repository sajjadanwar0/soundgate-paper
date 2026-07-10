# probes-temporal/ — durable-execution contrast arm (paper Sec. 3.4)

The Section-3 predicates executed on Temporal, the durable-execution engine
reviewers name as the re-architecture alternative. Contrast arm in the FW-E
sense: excluded from every recurrence denominator; the sibling bit is
behavioral only (Temporal's docs imply no cross-branch pause).

## Contents
- `probe_temporal.py`        — T1 sibling+reject, T2 replay, T3/T3b cancel
  (no-heartbeat / heartbeating), T4 timeout.
  Every activity: RetryPolicy(maximum_attempts=1).
- `probe_temporal_gated.py`  — T5: the repaired T1 twin. The ~20-line wrapper
  (pip install soundgate) holds the sibling during
  a live Signal pause; reject → 0 effects, sticky;
  control effect releases. In-process Gate by
  default; set SOUNDGATE_ADDR=127.0.0.1:8796 to
  drive the external Rust gate (paper-preferred
  reference-monitor mode).

## Run
    # 1. real local Temporal server (no account, no keys)
    temporal server start-dev --headless --ip 127.0.0.1 --port 7233

    # 2. deps (pin whatever you install; the transcript header records them)
    pip install temporalio soundgate

    # 3. probes → receipts (2>&1: the stderr noise lines are evidentiary,
    #    see "Known-benign transcript noise" below)
    python probe_temporal.py       2>&1 | tee ../soundgate/evidence/temporal_probes.txt
    python probe_temporal_gated.py 2>&1 | tee ../soundgate/evidence/temporal_gated.txt

    # 4. optional: external-gate mode for T5
    (cd ../soundgate && cargo run --release &)          # gate on 127.0.0.1:8796
    SOUNDGATE_ADDR=127.0.0.1:8796 python probe_temporal_gated.py

    # env overrides: TEMPORAL_ADDRESS=host:port (default 127.0.0.1:7233)

## House rules before any bit enters the paper
- Rerun verdict-identically on >=3 independent environments (Sec. 3.1
  standard); the paper's Sec. 3.4 carries an ENV-COUNT TODO comment marking
  where the environment sentence goes.
- Pin your exact versions per environment (the transcript header records
  CLI/server, temporalio, python). Reference runs to date, all six verdicts
  identical: CLI 1.7.3 / Server 1.31.2 and CLI 1.7.2 / Server 1.31.1, both
  temporalio 1.30.0 — i.e., two server minor versions already covered.
- Add the reproduce.sh check: extract the six verdict lines from
  evidence/temporal_probes.txt and the T5 PASS lines from
  evidence/temporal_gated.txt; FAIL honestly if a receipt is missing.

## Known-benign transcript noise
- Rust-core WARN "Activity not found on completion ... already been cancelled
  but completed anyway" during T3/T4: Temporal's own runtime observing the
  orphan/zombie completing after the caller moved on — corroborating
  evidence, keep it in the receipt.
- Python-side "Completing activity as failed" + CancelledError traceback
  during T3b: this IS the clean contrast working — the heartbeat delivered
  the cancellation, the activity raised CancelledError before its commit
  point, and the SDK logged the cancelled completion. Zero effects follow.
  It is emitted on stderr, hence the 2>&1 in the run commands.
- T2's detail field `workflow_reports_replayed: False` is expected: the final
  workflow task executes past the replay boundary. The replay proof is the
  cache-off worker restart plus the 1→1 effect count.