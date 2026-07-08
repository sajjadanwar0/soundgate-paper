"""Shared probe machinery: an event log and a pre-registered violation record.

The probes are model-free: nodes/steps are plain Python functions, because the
questions under test are properties of the FRAMEWORK's control flow, not of any
LLM. Effects are represented as event-log appends so we can observe exactly when
and how many times an effect occurs relative to a pause/reject/cancel/timeout.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class EventLog:
    events: list[str] = field(default_factory=list)

    def log(self, tag: str) -> None:
        self.events.append(tag)

    def count(self, tag: str) -> int:
        return self.events.count(tag)

    def contains(self, substr: str) -> bool:
        return any(substr in e for e in self.events)

    def clear(self) -> None:
        self.events.clear()


@dataclass
class ProbeResult:
    name: str
    violation: bool
    detail: dict

    def line(self) -> str:
        status = "VIOLATION" if self.violation else "clean/contrast"
        return f"{self.name:<32} -> {status}  {self.detail}"


def summarize(results: list[ProbeResult]) -> str:
    v = sum(r.violation for r in results)
    body = "\n".join(r.line() for r in results)
    return f"{body}\n\nVIOLATION AXES CONFIRMED: {v}/{len(results)}"
