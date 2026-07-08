"""Unit tests for the shared harness (model-free, no framework needed)."""
from agentprobe._harness import EventLog, ProbeResult, summarize


def test_eventlog_counts():
    log = EventLog()
    log.log("a"); log.log("a"); log.log("b")
    assert log.count("a") == 2
    assert log.contains("b")
    log.clear()
    assert log.events == []


def test_summarize_counts_violations():
    rs = [
        ProbeResult("x", True, {}),
        ProbeResult("y", False, {}),
        ProbeResult("z", True, {}),
    ]
    out = summarize(rs)
    assert "2/3" in out
