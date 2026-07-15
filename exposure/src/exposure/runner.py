from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from dataclasses import dataclass
from openai import OpenAI
from .tasks import SYSTEM_PROMPT, Task, Tool, get_tasks
import anthropic

SEED_BASE = 1000
CLIENT_TIMEOUT_S = 90
CLIENT_MAX_RETRIES = 4

@dataclass
class TurnRecord:
    tool_calls: list[str]
    had_text: bool

@dataclass
class RunRecord:
    experiment: str
    task_id: str
    task_class: str
    provider: str
    model: str
    run_idx: int
    temperature: float
    turns: list[dict]
    consequential_tool: str
    consequential_called: bool
    consequential_turn_idx: int | None
    siblings_in_consequential_turn: int | None
    parallel_exposure: bool
    stopped_reason: str
    error: str | None
    wall_s: float

class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, temperature: float):
        self.client = OpenAI(timeout=CLIENT_TIMEOUT_S, max_retries=CLIENT_MAX_RETRIES)
        self.model = model
        self.temperature = temperature

    def tool_schema(self, tools: tuple[Tool, ...]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def init_messages(self, task: Task) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task.user_msg},
        ]

    def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            seed=SEED_BASE + run_idx,
        )

        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        calls = [(c.id, c.function.name) for c in (msg.tool_calls or [])]

        return calls, bool(msg.content)

    def add_tool_results(self, messages: list[dict], results: list[tuple[str, str, str]]):
        for call_id, _name, payload in results:
            messages.append({"role": "tool", "tool_call_id": call_id, "content": payload})

class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, temperature: float):
        self.client = anthropic.Anthropic(
            timeout=CLIENT_TIMEOUT_S, max_retries=CLIENT_MAX_RETRIES
        )
        self.model = model
        self.temperature = temperature

    def tool_schema(self, tools: tuple[Tool, ...]) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]

    def init_messages(self, task: Task) -> list[dict]:
        return [{"role": "user", "content": task.user_msg}]

    def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
            temperature=self.temperature,
        )

        blocks = resp.content

        messages.append(
            {"role": "assistant",
             "content": [b.model_dump(exclude_none=True) for b in blocks]}
        )
        calls = [(b.id, b.name) for b in blocks if getattr(b, "type", "") == "tool_use"]
        had_text = any(getattr(b, "type", "") == "text" and getattr(b, "text", "").strip() for b in blocks)

        return calls, had_text

    def add_tool_results(self, messages: list[dict], results: list[tuple[str, str, str]]):
        messages.append(
            {"role": "user",
             "content": [
                 {"type": "tool_result", "tool_use_id": call_id, "content": payload}
                 for call_id, _name, payload in results
             ]}
        )

class MockProvider:
    name = "mock"

    def __init__(self, model: str, temperature: float):
        self.model = model
        self.temperature = temperature

    def tool_schema(self, tools: tuple[Tool, ...]) -> list[dict]:
        return [{"name": t.name} for t in tools]

    def init_messages(self, task: Task) -> list[dict]:
        benign = [t.name for t in task.tools if not t.consequential]
        cons = task.consequential_tool
        self._task_plan = {
            0: [[cons, benign[0]]],
            1: [[benign[0]], [cons]],
            2: [[cons]],
            3: [[benign[1]], []],
        }
        self._turn_i = 0
        return [{"role": "user", "content": task.user_msg}]

    def set_run(self, run_idx: int):
        self._plan = self._task_plan[run_idx % 4]
        self._turn_i = 0

    def turn(self, messages: list[dict], tools: list[dict], run_idx: int):
        names = self._plan[self._turn_i] if self._turn_i < len(self._plan) else []
        self._turn_i += 1
        calls = [(f"call_{self._turn_i}_{i}", n) for i, n in enumerate(names)]
        return calls, not names  # text iff no tool calls (final answer)

    def add_tool_results(self, messages: list[dict], results):
        pass


PROVIDERS = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "mock": MockProvider}
DEFAULT_MODELS = {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-6", "mock": "mock-1"}

def run_one(provider, task: Task, run_idx: int, max_turns: int) -> RunRecord:
    t0 = time.monotonic()
    tools_by_name = {t.name: t for t in task.tools}
    cons = task.consequential_tool
    schema = provider.tool_schema(task.tools)
    messages = provider.init_messages(task)
    if isinstance(provider, MockProvider):
        provider.set_run(run_idx)

    turns: list[TurnRecord] = []
    called_idx: int | None = None
    siblings: int | None = None
    stopped = "max_turns"
    error = None
    try:
        for _ in range(max_turns):
            calls, had_text = provider.turn(messages, schema, run_idx)
            turns.append(TurnRecord([n for _, n in calls], had_text))
            if not calls:
                stopped = "final_answer"
                break
            names = [n for _, n in calls]
            if cons in names:
                called_idx = len(turns) - 1
                siblings = sum(1 for n in names if n != cons)
                stopped = "consequential"
                break
            results = [
                (cid, n, tools_by_name[n].canned_result or "{}") for cid, n in calls
            ]
            provider.add_tool_results(messages, results)
    except Exception as e:
        stopped, error = "error", f"{type(e).__name__}: {e}"

    return RunRecord(
        experiment="E-EXPOSURE",
        task_id=task.task_id,
        task_class=task.klass,
        provider=provider.name,
        model=provider.model,
        run_idx=run_idx,
        temperature=provider.temperature,
        turns=[dataclasses.asdict(t) for t in turns],
        consequential_tool=cons,
        consequential_called=called_idx is not None,
        consequential_turn_idx=called_idx,
        siblings_in_consequential_turn=siblings,
        parallel_exposure=called_idx is not None and (siblings or 0) >= 1,
        stopped_reason=stopped,
        error=error,
        wall_s=round(time.monotonic() - t0, 3),
    )

def load_done(path: str, provider: str, model: str) -> set[tuple[str, int]]:
    """(task_id, run_idx) keys with a non-error record for this provider+model."""
    done: set[tuple[str, int]] = set()
    if not os.path.exists(path):
        return done
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("error"):
                continue
            if r.get("provider") == provider and r.get("model") == model:
                done.add((r["task_id"], r["run_idx"]))
    return done

def main() -> None:
    ap = argparse.ArgumentParser(description="E-EXPOSURE runner (see tasks.py)")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    ap.add_argument("--model", default=None, help="default: per-provider default")
    ap.add_argument("--runs", type=int, default=25, help="runs per task (default 25)")
    ap.add_argument("--tasks", default=None, help="comma-separated task ids (default: all 10)")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--max-turns", type=int, default=5)
    ap.add_argument("--out", default=None, help="JSONL path (default results/exposure_<provider>_<model>.jsonl)")
    ap.add_argument("--smoke", action="store_true", help="1 task x 1 run (burn pennies before the batch)")
    args = ap.parse_args()

    model = args.model or DEFAULT_MODELS[args.provider]
    tasks = get_tasks(args.tasks.split(",") if args.tasks else None)
    runs = args.runs

    if args.smoke:
        tasks, runs = tasks[:1], 1

    if args.provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set")
    if args.provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set")

    out = args.out or f"results/exposure_{args.provider}_{model.replace('/', '_')}.jsonl"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    done = load_done(out, args.provider, model)
    provider = PROVIDERS[args.provider](model, args.temperature)

    todo = [(t, i) for t in tasks for i in range(runs) if (t.task_id, i) not in done]
    skipped = len(tasks) * runs - len(todo)

    if skipped:
        print(f"RESUME: {skipped} run(s) already recorded in {out}; {len(todo)} to go")

    if not todo:
        print("nothing to do")
        return

    done_n = 0
    with open(out, "a") as fh:
        for task, run_idx in todo:
            rec = run_one(provider, task, run_idx, args.max_turns)
            fh.write(json.dumps(dataclasses.asdict(rec)) + "\n")
            fh.flush()
            done_n += 1
            tag = "EXPOSURE" if rec.parallel_exposure else rec.stopped_reason
            print(f"[{done_n:>3}/{len(todo)}] {task.task_id:<22} run {run_idx:>2} -> {tag}"
                  + (f"  ({rec.error})" if rec.error else ""))
    print(f"\nwrote {out}")

try:
    from .providers_openrouter import NEW_PROVIDERS, NEW_DEFAULT_MODELS
    PROVIDERS.update(NEW_PROVIDERS)
    DEFAULT_MODELS.update(NEW_DEFAULT_MODELS)
except Exception:
    pass

try:
    from .providers_native import NATIVE_PROVIDERS, NATIVE_DEFAULT_MODELS
    PROVIDERS.update(NATIVE_PROVIDERS)
    DEFAULT_MODELS.update(NATIVE_DEFAULT_MODELS)
except Exception:
    pass

if __name__ == "__main__":
    main()