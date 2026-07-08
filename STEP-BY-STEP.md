# STEP-BY-STEP.md

Concrete instructions to build the paper, run every experiment, extend the
study, and finish the build phase. Nothing here needs an API key.

--------------------------------------------------------------------------
## 0. Prerequisites
- **Rust** (stable): `rustc`/`cargo`. You already have this in RustRover.
- **uv** (Python): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node >= 18** + npm (for the LangGraph.js column; AbortSignal.timeout).
- **LaTeX**: TeX Live *full* (for `IEEEtran.cls`), or install the class:
  `tlmgr install ieeetran cite`  (Overleaf has it built in).

--------------------------------------------------------------------------
## 1. Build the paper
```bash
cd paper
latexmk -pdf soundgate.tex        # produces soundgate.pdf
# or, without latexmk:
pdflatex soundgate.tex && bibtex soundgate && pdflatex soundgate.tex && pdflatex soundgate.tex
```
Notes:
- The preamble is IEEE-Computer-Society compliant: it uses
  `\documentclass[10pt,journal,compsoc]{IEEEtran}` and does **not** load
  `mathptmx/helvet/courier` or alter `fontenc/inputenc`. IEEEtran selects
  Palatino automatically for compsoc journals; overriding fonts is the #1
  desk-reject formatting flag, which is why your original stack was removed.
- SINGLE-FILE CONVENTION: the bibliography lives inline in the
  `thebibliography` environment at the end of `soundgate.tex`. There is no
  external `.bib` and no bibtex pass; add real entries directly there.
  Compile is `pdflatex` x2 (or `latexmk -pdf`).
- Fill your e-mail and the artifact URL in the `\author` block.

--------------------------------------------------------------------------
## 2. Run the Python measurement suites (uv)

The main environment hosts FW-A, FW-B, FW-C, FW-D. CrewAI (FW-E) gets its
own environment because installing it downgrades 8 packages of the closure
the other verdicts were recorded under (see `pyproject.toml` comments; the
`[tool.uv] conflicts` table makes `uv sync --all-extras` fail loudly on
purpose).

```bash
cd probes

# Main env: FW-A langgraph, FW-B llama-index, FW-C msaf, FW-D openai sdk
uv sync --extra msaf --extra openai-sdk
uv run --no-sync agentprobe-langgraph  | tee results/langgraph_py.txt
uv run --no-sync agentprobe-llamaindex | tee results/llamaindex.txt
uv run --no-sync agentprobe-msaf       | tee results/msaf.txt
uv run --no-sync agentprobe-openai     | tee results/openai_agents.txt
uv run --no-sync pytest                # harness tests + verdict regression
                                       # guards (pinned verdict map per suite;
                                       # ~30-60 s, real sleeps inside probes)

# Isolated env: FW-E crewai
UV_PROJECT_ENVIRONMENT=.venv-crewai uv sync --extra crewai
CREWAI_DISABLE_TELEMETRY=true OTEL_SDK_DISABLED=true \
  UV_PROJECT_ENVIRONMENT=.venv-crewai uv run --no-sync agentprobe-crewai \
  | tee results/crewai.txt
```

`uv.lock` is committed; `uv sync` reproduces the exact closure. The freezes
the recorded verdicts were captured under are committed in
`results/env/freeze-*.txt` (audit trail if a future lock re-resolve drifts).

**Determinism reps.** Verdicts were identical across 5/5 repetitions per
suite (30/30 for the FW-A core probes in the earlier pass). Raw logs:
`results/reps/<suite>/rep{1..5}.txt`. To regenerate:
```bash
for i in 1 2 3 4 5; do uv run --no-sync agentprobe-msaf > results/reps/msaf/rep$i.txt; done
# ... same pattern per suite
```

**Version-stability check (a paper claim).** The study reports two LangGraph
releases. To reproduce:
```bash
uv add "langgraph==1.2.6" && uv run agentprobe-langgraph | tee results/langgraph_1_2_6.txt
uv add "langgraph==1.2.7" && uv run agentprobe-langgraph | tee results/langgraph_1_2_7.txt
```

--------------------------------------------------------------------------
## 3. Run the LangGraph.js suite (FW-F, Node)
```bash
cd probes-js
npm ci                # exact versions from package-lock.json
npm run probe | tee ../probes/results/langgraph_js.txt
```
Host-language datum this column exists for: JS promises are not cancellable;
`config.signal` (the framework's documented, native cancellation surface)
makes the caller stop waiting but does not interrupt the node, so the
cancellation and timeout axes violate even for pure-async node code that is
cleanly cancellable under Python asyncio.

--------------------------------------------------------------------------
## 4. Run the repair (Rust / soundgate)
```bash
cd soundgate
cargo test --release                      # 11/11: 7 property tests + 4 G1
                                          # regression tests (cross-run scoping)
cargo build --release
python3 e2e/e2e_test.py                    # drives the LIVE gate over TCP
                                           # (6/6 incl. WAL crash-restart S5;
                                           # durable mode: soundgate ADDR WAL_PATH):
                                           # 5/5 blocked/scoped (incl. the G1
                                           # cross-run counterexample) + 1 legit released
```
To benchmark per-effect latency, add the `criterion` dev-dependency and bench
target shown in `soundgate/Cargo.toml` comments, then `cargo bench`.
Measured overhead of the current gate (loopback TCP, 20k round-trips):
median 13.0 us, p95 22.5 us, p99 37.7 us (~66.5k admissions/s single client).

--------------------------------------------------------------------------
## 5. Extend the study to another framework
1. Introspect the installed API from source — never code the probe from
   memory of the docs. Record the introspection notes in the module
   docstring.
2. Create `src/agentprobe/<fw>_probes.py`:
    - build a minimal workflow with an approval gate + a sibling effect;
    - represent every side effect as `LOG.log("EFFECT:...")`;
    - fix the violation predicate in the docstring **before** first run;
    - mark axes that cannot be probed as NOT PROBED — never fake a row;
    - return `ProbeResult(name, violation, detail)`.
3. Add the extra + pin and a console script in `pyproject.toml`; declare a
   `[tool.uv]` conflict if the framework mutates the shared closure
   (measure it: `uv pip install --dry-run <fw>`).
4. `uv run agentprobe-<fw> | tee results/<fw>.txt`, run 5 determinism reps,
   commit outputs, add the row to `results/MATRIX.md` and the paper table.

Same axes each time: sibling approval leak, reject-after-effect, replay
(in-process + checkpoint-restore), cancellation (thread vs pure-async where
the split exists), timeout (native where it exists, host-level labeled as
such).

--------------------------------------------------------------------------
## 6. Wire soundgate into a framework's tool path (integration demo)
In the framework's tool-invocation wrapper, before performing a side effect:
1. open a socket to the running `soundgate` (default `127.0.0.1:8799`);
2. send `{"op":"submit","run_id":<run>,"effect_key":<idempotency key>,
   "needs_approval":<bool>}`;
3. perform the effect **only** on `{"verdict":"release"}`;
4. on approval UI decision send
   `{"op":"decide","effect_key":<key>,"approved":<bool>}`;
5. on run cancel/timeout send `{"op":"cancel","run_id":<run>}`.
   The idempotency key must be stable across replays of the same logical effect
   (e.g. hash of tool name + arguments + logical step id).

G1 FIXED: effect identity is now the pair `(run_id, effect_key)` throughout
(released/rejected/pending state), `decide` REQUIRES `run_id` on the wire,
approve-after-cancel reports `refused_cancelled` (not the old "duplicate"
misnomer), and cancel acks `{"verdict":"ack"}`. The counterexample lives on
as `g1_*` unit tests and e2e scenario S4. Still open for Phase 4:
authentication of `decide`, fail-closed persistence, bounded memory.

--------------------------------------------------------------------------
## 7. Remaining build-phase checklist (to reach submission)
- [x] MS Agent Framework, OpenAI Agents SDK, CrewAI probe modules + rows.
- [x] LangGraph.js column (cross-runtime replication + host-language datum).
- [x] Native-timeout rows where a native mechanism exists (FW-D per-tool
  timeout incl. sound-by-refusal; FW-E max_execution_time incl. the new
  blocking-overrun class); host-level rows labeled as such.
- [x] uv.lock + env freezes + 5x determinism reps committed.
- [x] E-EXPOSURE complete (Phase 3): gpt-4o exposure_given_called 0.15
  [0.11,0.20] (38/250), claude-sonnet-4-6 0.03 [0.01,0.05] (6/238);
  per-task peaks 0.84 (gpt-4o, compound_cleanup) and 0.24 (sonnet,
  compound_transfer). Canonical: exposure/results/EXPOSURE.md + JSONLs.
  TODO: one more `exposure-run --provider anthropic` to fill the 2
  error-only keys (compound_cleanup runs 14, 24), then regenerate.
- [x] Phase 5 rewrite complete: exposure + prevalence sections, expectation-audit
  table, Related Work engaging Atomix/SagaLLM/AgentSpec/Progent/CaMeL/
  Temporal/TOCTOU/MAST (all 14 bib entries live-verified, zero placeholders),
  failure-model subsection (durability/reachability/bounded-state/decide-auth),
  responsible-disclosure appendix, abstract+contributions synced. 7 pages,
  0 compile errors. REMAINING before submission: de-anonymize decision,
  2-key Anthropic resume refresh of Sec. exposure denominators, upstream
  issue filings (appendix commitment), full author read-through.
- [x] Paper Table 1 swapped to the six-framework matrix; the six stale
  framework-count claims and the "previously undocumented" overclaim
  fixed (evidence-sync only; full Phase-5 rewrite still pending).
- [x] FW-B (LlamaIndex) column completed: cancellation via native
  handler.cancel_run() -> VIOLATION (worker thread not covered by
  cooperative cancel, 5/5); replay via Context.to_dict/from_dict ->
  clean 1->1 (completed step not re-executed, design contrast). Matrix +
  paper table cells updated.
- [x] CrewAI Crew.from_checkpoint replay INVESTIGATED: NOT PROBED for a
  DOCUMENTED reason -- crewai serializes runtime state via
  model_dump(mode='json'), which raises PydanticSerializationError on the
  probe's tool function object, so no checkpoint is written for a
  tool-bearing crew. Effect fired once; nothing to resume from. Recorded
  honestly in matrix footnote 3 (not a fake clean).
- [ ] Out-of-process effect sink (Phase 0) retrofitted to all six suites.
- [x] Per-probe pytest regression guards (verdict snapshots; crewai
  variant: `scripts/check_crewai_verdicts.py` in its venv).
- [x] Criterion in-process latency: release ~380ns (~600ns @100k identities),
  held->approve ~575ns, duplicate hit ~136ns, cancel fence ~58ns; socket
  round-trip (13us median) dominates. MSRV pins (clap 4.4.18, half 2.2.1)
  keep cargo bench working from cargo 1.75.
- [x] E-E2E integration demo in REAL langgraph==1.2.7 (e2e/e2e_langgraph.py,
  run with probes/.venv python): 3/3 -- sibling held+refused during a real
  interrupt() pause; node body re-ran 2x but effect executed EXACTLY once
  (release -> refused_duplicate); zombie thread fenced after cancel.
  Twenty-line GateClient wrapper; zero framework modification.
- [x] Fix gate G1 (per-run key scoping; test-first, 11/11 + e2e S4).
- [x] Fail-closed WAL persistence: optional 2nd CLI arg = log path; fsync
  BEFORE acknowledge; recovery replays before listen; e2e S5 SIGKILLs the
  gate mid-run and shows both fences survive (6/6). Event/apply() in lib
  with idempotent-replay unit tests (13/13).
- [x] close_run/compaction: run-level fence + drops per-identity state;
  memory bounded by active runs. Soundness test: replayed effect from a
  closed run refuses via fence, not slip through as release.
- [x] Randomized invariant harness (stdlib, in lib.rs, 2000x40 ops) +
  feature-gated proptest suite (tests/proptest_invariants.rs; ONE command,
  the feature pulls the optional proptest dep itself:
  cargo test --features proptest-tests). FOUND & FIXED a real bug:
  resubmit-of-held-with-appr=false double-released via a stale pending
  entry; fix = idempotent hold. 16/16 unit tests, 6/6 + 3/3 e2e green.
- [ ] Phase 4 remainder (optional, non-blocking): decide() auth token.
- [x] External-review revision pass (4 reviewer reports addressed in tex):
  removed running header; scoped every universal claim ("does not hold in
  current frameworks TESTED", "one robust design" not "must", design-choice
  -> "avoidable, by design or fix"); QUARANTINED FW-E from recurrence counts
  (ominus 'not comparable' + dedicated subsection: missing primitive, not
  broken); reframed exposure as plan-shape EMISSION with N=25 Wilson-CI
  caveat; added Limitations section (mediation/snapshot/corpus/availability);
  strengthened barrier-contract evidence (3 sources, no false 'vendor
  promised' claim); added verifiable related work (Schneider security
  automata, obj-capability, fencing tokens, 2PC, Orseau&Armstrong
  interruptibility, Soares corrigibility -- ALL verified, NONE from the
  reviewers' likely-hallucinated suggestions); committed to mechanized
  proof in failure-model. 9 pages, 0 errors, 0 undefined cites.
- [x] MECHANIZED VERIFICATION -- three tiers written AND VERIFIED GREEN:
  TLC FOUND A REAL GATE BUG (late decide(reject) on a released id recorded
  a contradictory rejection -> released/rejected disjointness violated);
  Verus flagged the SAME transition (decide_preserves failed, 10/11).
  FIXED in lib.rs (released-check before not-pending reject ->
  RefusedDuplicate), mirrored in both models, pinned by
  i1_late_reject_of_released_is_duplicate + harness/proptest invariant 4.
  17/17 unit, 6/6 + 3/3 e2e green after fix. TLAPS SubmitPreserves/
  DecidePreserves rewritten as per-disjunct CASE splits.
  >>> ALL THREE TIERS VERIFIED GREEN ON HIS MACHINE (2026-07-03):
  Verus 11 verified/0 errors; TLC 729 distinct states/depth 7/0
  violations; TLAPS all 68 obligations proved; 17/17 unit + proptest.
  Paper's three-tier claim + "verification found a real bug" now fully
  backed by run artifacts. Commands to reproduce:
  Tier 1 Verus:  cd formal/verus && verus gate_model.rs
  Tier 2 TLC:    cd formal/tla  && tlc SoundGate.tla
  Tier 3 TLAPS:  cd formal/tla  && tlapm SoundGate_Proofs.tla
  formal/README.md has expected output + incremental-debug steps per tier
  if any version drift errors appear. Report concrete errors -> local fix.
  Liveness intentionally out of scope (depends on approver/framework).
- [x] Incident corpus built (Phase 2): corpus/results/INCIDENTS.md, 11 direct
  incidents (A1 x5, A2 x6) + adjacent/context, verbatim queries recorded.
  Enrichment RUN (2026-07-03, authenticated): zero title/date mismatches
  across all 14 GitHub rows; #6158 corrected to merged PR; authoritative
  states in corpus/results/incidents_enriched.jsonl.
- [x] Inline bibliography populated: 14 entries, every one live-verified
  (Atomix, SagaLLM/PVLDB, Sagas'87, AgentSpec, Progent, CaMeL, MAST,
  2x TOCTOU, Temporal, Helland, LangGraph docs, practitioner post,
  self-cite arXiv:2606.17182). Zero placeholders.
- [ ] YOUR SIDE -- file upstream issues (responsible disclosure) for the
  not-yet-tracked behaviors named in the paper's appendix (sibling leak
  on FW-B/C/D, JS AbortSignal orphan, blocking-timeout class) BEFORE the
  manuscript is public; record filing status in this checklist.
- [ ] YOUR SIDE -- two-key Anthropic resume (compound_cleanup runs 14, 24),
  then regenerate EXPOSURE.md and refresh the %% REFRESH-marked
  denominators in paper/soundgate.tex.
- [x] FINAL CONSISTENCY SWEEP (pre-submission gate): every numeric claim
  cross-checked vs source. Exposure (0.15/0.03 pooled, 250/250 & 238/248
  called, 0.84 cleanup, 0.24 transfer, 0.04 gpt-transfer, 10-of-25
  cancel_sub declination) ALL match EXPOSURE.md. Corpus 11 direct / 3
  adjacent / 6 context and 5 sibling / 6 replay ALL match seeds.py. Formal
  claims (all-obligations / 0-violations) match run outputs. Refs/cites:
  0 broken refs, 0 broken cites, 20/20 bibitems cited, 20/20 keys resolved.
  FIXED: duplicate label sec:eval (multiply-defined warning); added the
  missing Table~ref{tab:exposure} in prose. 9 pages, 0 errors, 0 warnings.
  OPEN DECISION: overhead numbers (13.0us socket / 380ns bench) are SANDBOX
  figures; his machine is faster -- decide whether to regenerate on his
  hardware for camera-ready so all figures share one provenance.
- [ ] YOUR SIDE -- de-anonymization decision (FW-A..F vs named frameworks;
  interacts with venue: double-anonymous TOSEM keeps letters, arXiv-first
  names them) and full author read-through of the 9-page draft
  BEFORE submission; de-anonymize framework names in text.

--------------------------------------------------------------------------
## 8. Pre-registered kill condition (honest scoping)
If, once the matrix is filled, every *other* framework proves sound on every
axis AND the LangGraph behaviors are patched upstream before submission, the
contribution narrows toward a two-framework case study — reassess target venue
accordingly. Current evidence closes this off: the sibling leak reproduces on
five execution models across six framework columns and two language runtimes,
and FW-E contributes a new violation class (`timeout_blocks_then_effect`).