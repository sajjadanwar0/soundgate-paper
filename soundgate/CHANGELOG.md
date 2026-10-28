# Changelog

## Unreleased

### Changed
- `pyo3` 0.23 → 0.29 (RUSTSEC-2025-0020, RUSTSEC-2026-0177). The binding
  keeps `abi3-py38`; `Python::allow_threads` became `Python::detach`, and
  `Verdict` opts into `from_py_object` explicitly. No Python-visible change.
- `Cargo.lock`: rustls 0.23.46, rustls-webpki 0.103.16, h2 0.4.20,
  crossbeam-epoch 0.9.21, tokio 1.54.1 (RustSec advisories against the
  previous pins; none reachable from the shipped binary or wheel). `cargo
  audit` reports no vulnerabilities.

## 0.1.4 — 2026-10-28

### Fixed
- **A rejection or release could be forgotten across two restarts of the
  durable server.** Recovery skipped a torn final record but left its bytes
  in the log; the next acknowledged decision was appended on the same line;
  the following recovery skipped the merged, unparsable line as a "torn final
  record" and the decision was gone while its bytes remained on disk. A lost
  rejection let a refused effect run; a lost release allowed a duplicate.
  Reported by **Cenab Batu Bora (Georgia Tech)**, *A Restart Is Not
  Permission: When an Agent Gate Forgets "No"*, Apart Research
  incident-response sprint, 11 September 2026, against soundgate 0.1.3 at
  commit `6568403`. The report also proposed the repair adopted here.

### Added
- **Recovery barrier** (`src/main.rs`), run before the listener opens:
  exclusive lock on the WAL for the life of the process; every
  newline-terminated record must parse or the gate refuses to start; an
  unterminated tail is completed (whole record) or truncated (fragment); the
  repair is fsynced before replay. The lock is re-taken after every
  compaction.
- **Fail-closed appends**: a failed or partial append stops the process
  instead of leaving a fragment for the next append to land on.
- **Regression test** `tests/wal_recovery_barrier.rs`: Bora's byte-prefix
  sweep (every prefix of a three-record log × one acknowledged decision ×
  crash × restart, 268 histories), plus two guards: a log already merged by
  0.1.3 is refused rather than silently trimmed, and a second gate on the
  same WAL is refused. On the 0.1.3 recovery code the sweep loses the
  decision in 260 of 268 histories and leaves 260 malformed logs; on 0.1.4
  all counts are zero.
- The server prints the address it actually bound (`127.0.0.1:0` is usable
  in tests).

### Unchanged
- The admission rules, the group-commit lemma and the verified model: the
  defect was at the boundary between the writer and recovery, which the
  single-restart test (S5) did not cover. The in-process Python gate has no
  WAL and is unaffected.

### Operators
- A log damaged by 0.1.3 (a merged line) makes 0.1.4 refuse to start with
  `WAL record N is unparsable`. Inspect the line; restoring the records it
  merged by hand is the only safe repair. Deleting the line forgets whatever
  decisions it held.

## 0.1.3 — 2026-07-15
- First PyPI release of the Rust core with PyO3 bindings and the
  line-JSON/TCP server.
