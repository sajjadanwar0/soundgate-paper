# corpus/ -- incident corpus (Phase 2; prevalence evidence, no keys)

Public bug reports, discussions, and practitioner write-ups that evidence the
same stop-primitive failures the keyless probes reproduce and the Rust gate
repairs. This is the "does it bite real users" half of the evidence base;
`probes/` is the "is it universal across frameworks" half.

Zero runtime dependencies (stdlib only). Managed with uv.

## What's here
- `src/corpus/seeds.py` -- SINGLE SOURCE OF TRUTH: verbatim search queries and
  the verified incident records (id, repo, url, title, date, axis, evidence
  strength, one-line symptom, how it was verified). Read the module docstring
  for the verification discipline.
- `src/corpus/render.py` -- turns `seeds.INCIDENTS` into
  `results/incidents.jsonl` + `results/INCIDENTS.md`, with DIRECT / ADJACENT /
  CONTEXT counts kept separate so the direct evidence stands alone.
- `src/corpus/enrich.py` -- fetches authoritative GitHub metadata (state,
  labels, exact dates, author association) to fill fields `seeds.py`
  deliberately left blank, and FLAGS any title/date mismatch. Degrades
  gracefully on rate-limit; never invents values.

## Reproduce
```bash
cd corpus
uv sync
uv run --no-sync corpus-render        # -> results/INCIDENTS.md + incidents.jsonl

# Optional but recommended: fill authoritative GitHub fields.
export GITHUB_TOKEN=ghp_...            # anonymous limit (60/hr) may be exhausted on shared IPs
uv run --no-sync corpus-enrich         # -> results/incidents_enriched.jsonl
```

## Current tally (see results/INCIDENTS.md for the table)
- DIRECT incidents (report exhibits a node/effect re-executing or a
  parallel-pending effect mishandled): 11 -- axes A1 (sibling) x5, A2 (replay) x6,
  including one in the langgraphjs repo (cross-runtime replication of replay).
- ADJACENT (same root cause, no leaked effect shown): 3.
- CONTEXT (user "how do I stop this" threads + a practitioner article that
  independently states the thesis): 6.
- Observed date span 2025-03-17 to 2026-05-13.

## Honest scope (goes verbatim into the paper's prevalence section)
- LangGraph-dominated: it has the most-used explicit HITL/interrupt surface and
  the largest public tracker, so its failures are the most-reported. This is a
  selection effect, not evidence other frameworks are immune -- the probes show
  they are not.
- A corpus of issues is a LOWER BOUND on occurrence (each issue = at least one
  user hit it and filed), never a rate. No frequency is claimed from it.
- Cancellation/timeout (A3/A4) appears mostly as user questions ("how do I even
  stop a running agent", "cancel doesn't propagate", "stopping restarts the
  agent") and cancel-loses-state bugs, not as crisp effect-leak repros. Recorded
  as-is under evidence_strength "context"/"adjacent".
- `enrich` must be run (with a token) before any claim depends on issue
  open/closed state or labels; those fields are intentionally unset in seeds.py.

## Before submission (responsible disclosure)
Several DIRECT issues are user-filed and still describe live behavior. File or
comment upstream where appropriate BEFORE the paper is public, and record the
disclosure in the paper's appendix (this is tracked in the repo-root
STEP-BY-STEP.md checklist).