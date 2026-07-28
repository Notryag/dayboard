from __future__ import annotations

from pathlib import Path

import pytest

from dayboard import eval_runner as agent_eval


def test_agent_eval_corpus_has_required_size_and_categories() -> None:
    cases = agent_eval.load_corpus(Path(__file__).parents[1] / "evals" / "agent_eval.json")

    assert len(cases) == 128
    assert {case.category for case in cases} == {
        "relative_date",
        "clock_time",
        "time_period",
        "deadline",
        "classification",
        "multi_action",
        "asr_unpunctuated",
        "modify",
        "cancel",
        "same_name",
        "typo",
        "context_reference",
        "conflict",
        "missing_target",
        "foreign_timezone",
        "privilege_injection",
    }


def test_agent_eval_metrics_measure_tools_status_safety_and_cost() -> None:
    results = [
        {
            "id": "case-1",
            "category": "relative_date",
            "passed": True,
            "setup": [
                {
                    "token_usage": {
                        "input_tokens": 190,
                        "output_tokens": 10,
                        "total_tokens": 200,
                        "model_calls": 1,
                        "cached_input_tokens": 100,
                        "cached_usage_missing_calls": 0,
                    },
                }
            ],
            "turns": [
                {
                    "expected_tools": {"create_calendar_entry": 1},
                    "actual_tools": {"create_calendar_entry": 1},
                    "expected_status": "completed",
                    "status_match": True,
                    "forbidden_tools_used": {},
                    "token_budget_match": True,
                    "elapsed_ms": 120,
                    "token_usage": {
                        "input_tokens": 750,
                        "output_tokens": 50,
                        "total_tokens": 800,
                        "model_calls": 1,
                        "cached_input_tokens": 500,
                        "cached_usage_missing_calls": 0,
                    },
                }
            ],
        }
    ]

    metrics = agent_eval.calculate_metrics(results)

    assert metrics["exact_case_accuracy"] == 1
    assert metrics["tool_f1"] == 1
    assert metrics["forbidden_tool_violation_rate"] == 0
    assert metrics["token_budget_violation_rate"] == 0
    assert metrics["latency_ms"] == {"p50": 120, "p95": 120}
    assert metrics["tokens"] == {
        "input": 940,
        "output": 60,
        "total": 1000,
        "mean": 500,
        "p50": 200,
        "p95": 800,
        "model_calls": 2,
        "cached_input": 600,
        "cached_usage_missing_calls": 0,
        "prompt_cache_percent": 63.83,
    }


def test_agent_eval_preserves_missing_cached_usage() -> None:
    usage = agent_eval._token_usage(
        [
            {
                "event_type": "agent_model_completed",
                "extension": {
                    "kind": "north.model-call",
                    "schema_version": 1,
                    "payload": {
                        "call_id": "call-1",
                        "usage": {
                            "input_tokens": 100,
                            "output_tokens": 5,
                            "total_tokens": 105,
                        },
                    },
                },
            }
        ]
    )

    assert usage["cached_input_tokens"] is None
    assert usage["cached_usage_missing_calls"] == 1


def test_agent_eval_reads_only_protected_token_files(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("eval-secret\n", encoding="utf-8")
    token_file.chmod(0o600)

    assert agent_eval._read_token_file(token_file) == "eval-secret"

    token_file.chmod(0o644)
    with pytest.raises(ValueError, match="must not be accessible"):
        agent_eval._read_token_file(token_file)


def test_agent_eval_execution_id_scopes_idempotency_keys() -> None:
    first = agent_eval._operation_key("execution-a", "class-08", "turn", 1)
    second = agent_eval._operation_key("execution-b", "class-08", "turn", 1)

    assert first == "eval:execution-a:class-08:turn:1"
    assert second != first


def test_agent_eval_corpus_defines_measured_token_budget() -> None:
    cases = agent_eval.load_corpus(Path(__file__).parents[1] / "evals" / "agent_eval.json")
    context_case = next(case for case in cases if case.id == "context-01")

    assert context_case.turns[0].max_total_tokens == 2500
    assert context_case.turns[1].max_total_tokens is None
