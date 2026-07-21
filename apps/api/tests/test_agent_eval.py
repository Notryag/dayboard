from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "agent_eval.py"
SPEC = importlib.util.spec_from_file_location("dayboard_agent_eval_test", SCRIPT_PATH)
assert SPEC and SPEC.loader
agent_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent_eval
SPEC.loader.exec_module(agent_eval)


def test_agent_eval_corpus_has_required_size_and_categories() -> None:
    cases = agent_eval.load_corpus(Path(__file__).parents[1] / "evals" / "agent_eval.json")

    assert len(cases) == 128
    assert {case.category for case in cases} == {
        "relative_date", "clock_time", "time_period", "deadline", "classification",
        "multi_action", "asr_unpunctuated", "modify", "cancel", "same_name", "typo",
        "context_reference", "conflict", "missing_target", "foreign_timezone",
        "privilege_injection",
    }


def test_agent_eval_metrics_measure_tools_status_safety_and_cost() -> None:
    results = [{
        "id": "case-1",
        "category": "relative_date",
        "passed": True,
        "turns": [{
            "expected_tools": {"create_calendar_entry": 1},
            "actual_tools": {"create_calendar_entry": 1},
            "expected_status": "completed",
            "status_match": True,
            "forbidden_tools_used": {},
            "elapsed_ms": 120,
            "token_usage": {"total_tokens": 800},
        }],
    }]

    metrics = agent_eval.calculate_metrics(results)

    assert metrics["exact_case_accuracy"] == 1
    assert metrics["tool_f1"] == 1
    assert metrics["forbidden_tool_violation_rate"] == 0
    assert metrics["latency_ms"] == {"p50": 120, "p95": 120}
    assert metrics["tokens"]["mean"] == 800
