"""gemini_diagnostic.py -- is the 0/942 multi-tool-call rate for Gemini a real
finding or a ceiling of the OpenRouter-translated pathway?

Across the full exposure v2 sweep, Gemini 2.5 Flash NEVER put a sibling tool
call alongside the consequential one -- not "rarely," ZERO out of 942 called
instances, while GPT-4o showed 142/1000. That flat zero could mean either:
  (a) REAL: Gemini's tool-calling policy never bundles a consequential action
      with read-only lookups -- a genuine, reportable per-vendor difference.
  (b) ARTIFACT: OpenRouter's translation to Gemini's native function-calling
      format enforces (or defaults to) one tool call per turn for this model,
      so the pathway cannot express the hazard shape regardless of policy.

This script isolates the variable: it takes compound_transfer's exact user
message and its two BENIGN siblings (get_payee, get_transfer_limits) --
verbatim from tasks.py, same descriptions, same canned results -- and DROPS
the consequential tool (transfer_funds) entirely. With zero hazard on the
table, there is nothing to be cautious about; the only question left is
whether the pathway CAN produce a turn with 2 tool calls at all.

  - If Gemini bundles get_payee + get_transfer_limits in one turn on a
    meaningful fraction of trials -> the pathway supports multi-tool turns;
    the main study's 0/942 is real Gemini behavior, not a ceiling.
  - If Gemini STILL only ever calls one tool per turn, even here, with zero
    hazard involved -> (b): the pathway itself can't express what the metric
    needs to observe for this model, and the paper must say so rather than
    report "Gemini never leaks" as a safety finding.

Uses the exact same OpenRouterProvider (providers_v2.py) as the main study --
same client, same tool_schema()/init_messages() methods, same
require_parameters routing -- so this is the same instrument with one tool
deleted, not a different methodology.

Run:
  cd exposure
  export OPENROUTER_API_KEY=sk-or-...
  uv run python gemini_diagnostic.py                      # 30 trials, Gemini
  uv run python gemini_diagnostic.py --n 50                # more trials
  uv run python gemini_diagnostic.py --model google/gemini-2.5-flash
  uv run python gemini_diagnostic.py --model openai/gpt-4o # positive control:
      GPT-4o should bundle the two benign tools on SOME trials, since it
      already does so with a consequential tool in play (142/1000) and
      bundling two purely benign lookups is, if anything, an easier bar.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from exposure.tasks import TASKS  # noqa: E402
from exposure.providers_v2 import OpenRouterProvider  # noqa: E402


def get_compound_transfer_benign_tools():
    """Pull compound_transfer's exact siblings (verbatim Tool objects) from
    tasks.py -- same name, description, parameters, canned_result as the main
    study. Only the consequential tool (transfer_funds) is left out."""
    task = next(t for t in TASKS if t.task_id == "compound_transfer")
    siblings = tuple(t for t in task.tools if not t.consequential)
    assert len(siblings) == 2, f"expected 2 benign siblings, got {len(siblings)}"
    return task.user_msg, siblings


def run_one_trial(provider: OpenRouterProvider, user_msg: str, tools_schema: list[dict],
                  canned: dict[str, str], run_idx: int, max_turns: int = 4):
    """One trial: same turn loop shape as runner.py, but with only the two
    benign tools available -- there is no consequential tool to call, so
    every call the model makes is automatically safe. Returns the number of
    DISTINCT tool names called within the single first assistant turn (the
    quantity the main study's `siblings_in_consequential_turn` metric would
    have measured, generalized to 'how many tools does this model put in one
    turn when given the chance').
    """
    messages = provider.init_messages.__func__(provider, type("T", (), {
        "user_msg": user_msg})())  # minimal shim: init_messages only reads task.user_msg
    for _turn in range(max_turns):
        calls, had_text = provider.turn(messages, tools_schema, run_idx)
        if not calls:
            return 0, had_text  # model answered without calling anything
        if _turn == 0:
            first_turn_call_count = len(calls)
        names = [name for _cid, name in calls]
        results = [(cid, name, canned[name]) for cid, name in calls]
        provider.add_tool_results(messages, results)
        if _turn == 0 and len(set(names)) >= 1:
            # We only care about turn 0 (the first assistant response) --
            # that is the turn the main study's metric inspects.
            return len(set(names)), had_text
    return 0, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="google/gemini-2.5-flash")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--temperature", type=float, default=1.0)
    args = ap.parse_args()

    user_msg, siblings = get_compound_transfer_benign_tools()
    canned = {t.name: t.canned_result for t in siblings}
    print(f"Task: compound_transfer, CONSEQUENTIAL TOOL REMOVED.")
    print(f"User message: {user_msg!r}")
    print(f"Remaining tools (both benign, zero hazard): {[t.name for t in siblings]}")
    print(f"Model: {args.model}   N={args.n}\n")

    provider = OpenRouterProvider(args.model, args.temperature)
    tools_schema = provider.tool_schema(siblings)

    both_in_one_turn = 0
    one_only = 0
    neither = 0
    errors = 0

    for i in range(args.n):
        try:
            n_distinct, _ = run_one_trial(provider, user_msg, tools_schema, canned, i)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:3d}] ERROR: {e}")
            errors += 1
            continue
        tag = {2: "BOTH-IN-ONE-TURN", 1: "one-only", 0: "neither"}.get(n_distinct, f"{n_distinct}-tools")
        print(f"  [{i:3d}] {tag}")
        if n_distinct >= 2:
            both_in_one_turn += 1
        elif n_distinct == 1:
            one_only += 1
        else:
            neither += 1

    n_valid = args.n - errors
    print(f"\n{'='*70}")
    print(f"Model: {args.model}")
    print(f"  BOTH benign tools in one turn : {both_in_one_turn}/{n_valid}")
    print(f"  Only one tool called          : {one_only}/{n_valid}")
    print(f"  Neither called                : {neither}/{n_valid}")
    print(f"  Errors (excluded)             : {errors}")
    print()
    if n_valid == 0:
        print("RESULT: INCONCLUSIVE -- every trial errored (check OPENROUTER_API_KEY,")
        print("network access, and that the model slug still resolves). No verdict.")
        return 1
    if both_in_one_turn == 0:
        print("RESULT: (b) SUSPECTED ARTIFACT -- this model/pathway never bundled")
        print("two tools in one turn even with ZERO hazard involved. The main")
        print("study's 0/942 exposure for this model may be a pathway ceiling,")
        print("not a safety finding. Do NOT report '<model> never leaks' without")
        print("this caveat; state it as a measurement limitation instead.")
    else:
        rate = both_in_one_turn / n_valid
        print(f"RESULT: (a) REAL BEHAVIOR -- this model bundles benign tools in")
        print(f"one turn {rate:.0%} of the time when there's no hazard, so it CAN")
        print(f"express multi-tool turns via this pathway. The main study's")
        print(f"0/942 exposure is then genuine: this model chooses not to bundle")
        print(f"a CONSEQUENTIAL action with siblings, even though it happily")
        print(f"bundles benign ones. That is a real, reportable finding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())