from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import time
from typing import Any
from uuid import uuid4

import httpx

from dayboard.eval_clarifications import (
    ClarificationFlowExpectation,
    clarification_is_consumed,
    inspect_clarification,
)
from dayboard.eval_oracles import (
    EvalTemplateContext,
    ExpectedScheduleItem,
    evaluate_schedule_expectations,
    render_expectation,
    render_template,
)


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "needs_clarification"}
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "dayboard-eval" / "token"


@dataclass(frozen=True, slots=True)
class EvalTurn:
    message: str
    expected_tools: dict[str, int]
    expected_status: str
    forbidden_tools: tuple[str, ...]
    max_total_tokens: int | None
    expected_schedule: tuple[ExpectedScheduleItem, ...]
    forbidden_response_substrings: tuple[str, ...] = ()
    clarification: ClarificationFlowExpectation | None = None


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    category: str
    setup: tuple[EvalTurn, ...]
    turns: tuple[EvalTurn, ...]
    category_min_accuracy: float | None = None


def _parse_eval_turn(raw: object, defaults: dict[str, Any]) -> EvalTurn:
    turn = {"message": raw} if isinstance(raw, str) else raw
    if not isinstance(turn, dict) or not isinstance(turn.get("message"), str):
        raise ValueError("every Agent Eval step must be a string or an object with message")
    return EvalTurn(
        message=turn["message"],
        expected_tools=dict(turn.get("expected_tools", defaults.get("expected_tools", {}))),
        expected_status=turn.get("expected_status", defaults.get("expected_status", "completed")),
        forbidden_tools=tuple(turn.get("forbidden_tools", defaults.get("forbidden_tools", []))),
        max_total_tokens=turn.get("max_total_tokens", defaults.get("max_total_tokens")),
        expected_schedule=tuple(
            ExpectedScheduleItem.model_validate(expectation)
            for expectation in turn.get("expected_schedule", defaults.get("expected_schedule", []))
        ),
        forbidden_response_substrings=tuple(
            turn.get(
                "forbidden_response_substrings",
                defaults.get("forbidden_response_substrings", []),
            )
        ),
        clarification=(
            ClarificationFlowExpectation.model_validate(turn["clarification"])
            if turn.get("clarification") is not None
            else None
        ),
    )


def load_corpus(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text())
    if payload.get("version") != 1:
        raise ValueError("unsupported Agent Eval corpus version")
    cases: list[EvalCase] = []
    for category in payload.get("categories", []):
        category_name = category["name"]
        defaults = category.get("defaults", {})
        for raw_case in category.get("cases", []):
            turns = [_parse_eval_turn(raw_turn, defaults) for raw_turn in raw_case["turns"]]
            setup = [_parse_eval_turn(raw_setup, {}) for raw_setup in raw_case.get("setup", [])]
            cases.append(
                EvalCase(
                    id=raw_case["id"],
                    category=category_name,
                    setup=tuple(setup),
                    turns=tuple(turns),
                    category_min_accuracy=category.get("min_accuracy"),
                )
            )
    validate_corpus(cases)
    return cases


def validate_corpus(cases: list[EvalCase]) -> None:
    if not 100 <= len(cases) <= 200:
        raise ValueError(f"Agent Eval corpus must contain 100-200 cases, found {len(cases)}")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Agent Eval case IDs must be unique")
    if any(not case.turns for case in cases):
        raise ValueError("every Agent Eval case must contain at least one evaluated turn")
    invalid_category_gates = [
        (case.category, case.category_min_accuracy)
        for case in cases
        if case.category_min_accuracy is not None
        and (
            isinstance(case.category_min_accuracy, bool)
            or not isinstance(case.category_min_accuracy, (int, float))
            or not 0 <= case.category_min_accuracy <= 1
        )
    ]
    if invalid_category_gates:
        raise ValueError(
            f"category accuracy gates must be between 0 and 1: {invalid_category_gates}"
        )
    invalid_budgets = [
        (case.id, turn.max_total_tokens)
        for case in cases
        for turn in case.turns
        if turn.max_total_tokens is not None
        and (
            isinstance(turn.max_total_tokens, bool)
            or not isinstance(turn.max_total_tokens, int)
            or turn.max_total_tokens <= 0
        )
    ]
    if invalid_budgets:
        raise ValueError(f"Agent Eval token budgets must be positive integers: {invalid_budgets}")
    variables = EvalTemplateContext.capture().variables(tag="validation")
    for case in cases:
        for turn in (*case.setup, *case.turns):
            render_template(turn.message, variables)
            for value in turn.forbidden_response_substrings:
                render_template(value, variables)
            for expectation in turn.expected_schedule:
                render_expectation(expectation, variables)
            if turn.clarification is not None:
                for values in (
                    turn.clarification.option_titles,
                    turn.clarification.option_local_starts,
                ):
                    for value in values or ():
                        render_template(value, variables)
                for expectation in turn.clarification.resume.expected_schedule:
                    render_expectation(expectation, variables)


def _read_token_file(path: Path) -> str:
    try:
        details = path.stat()
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("Eval token path must be a regular file")
        if details.st_size > 4096:
            raise ValueError("Eval token file is too large")
        if details.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ValueError("Eval token file must not be accessible by group or others")
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Could not read Eval token file: {path}") from exc
    if not token:
        raise ValueError("Eval token file is empty")
    return token


def _resolve_eval_token(token_file: Path | None) -> str | None:
    inline_token = os.getenv("DAYBOARD_EVAL_TOKEN", "").strip()
    selected_file = token_file
    if selected_file is None and DEFAULT_TOKEN_FILE.exists():
        selected_file = DEFAULT_TOKEN_FILE
    if inline_token and selected_file is not None:
        raise ValueError("Set only DAYBOARD_EVAL_TOKEN or an Eval token file, not both")
    if inline_token:
        return inline_token
    return _read_token_file(selected_file) if selected_file is not None else None


def _operation_key(execution_id: str, case_id: str, phase: str, index: int) -> str:
    return f"eval:{execution_id}:{case_id}:{phase}:{index}"


def _tool_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        if event.get("event_type") != "tool_call_completed":
            continue
        tool_name = _event_extension_payload(event, "north.tool-call").get("tool_name")
        if isinstance(tool_name, str):
            counts[tool_name] += 1
    return dict(counts)


def _token_usage(events: list[dict[str, Any]]) -> dict[str, int | None]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    seen_calls: set[str] = set()
    cached_input_tokens = 0
    cached_usage_missing_calls = 0
    for event in events:
        if event.get("event_type") != "agent_model_completed":
            continue
        metadata = _event_extension_payload(event, "north.model-call")
        call_id = metadata.get("call_id")
        if not isinstance(call_id, str) or not call_id or call_id in seen_calls:
            continue
        seen_calls.add(call_id)
        usage = metadata.get("usage") or {}
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
        cached = usage.get("cached_input_tokens")
        if isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0:
            cached_input_tokens += cached
        else:
            cached_usage_missing_calls += 1
    return {
        **totals,
        "model_calls": len(seen_calls),
        "cached_input_tokens": (cached_input_tokens if cached_usage_missing_calls == 0 else None),
        "cached_usage_missing_calls": cached_usage_missing_calls,
    }


def _event_extension_payload(
    event: dict[str, Any],
    expected_kind: str,
) -> dict[str, Any]:
    extension = event.get("extension")
    if not isinstance(extension, dict):
        raise ValueError(f"Run event is missing extension: {event.get('event_type')}")
    if extension.get("kind") != expected_kind or extension.get("schema_version") != 1:
        raise ValueError(f"Unexpected Run event extension: {extension}")
    payload = extension.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"Run event extension payload must be an object: {extension}")
    return payload


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    primary_turns = [turn for result in results for turn in result["turns"]]
    continuation_turns = [
        turn["clarification"]["resume"]
        for turn in primary_turns
        if isinstance(turn.get("clarification"), dict)
        and isinstance(turn["clarification"].get("resume"), dict)
    ]
    turns = [*primary_turns, *continuation_turns]
    usage_turns = [
        turn for result in results for turn in (*result.get("setup", []), *result["turns"])
    ]
    usage_turns.extend(continuation_turns)
    true_positive = false_positive = false_negative = 0
    category_counts: dict[str, list[bool]] = {}
    category_gates: dict[str, float] = {}
    for result in results:
        category_counts.setdefault(result["category"], []).append(result["passed"])
        if result.get("category_min_accuracy") is not None:
            category_gates[result["category"]] = result["category_min_accuracy"]
        for turn in result["turns"]:
            expected = Counter(turn["expected_tools"])
            actual = Counter(turn["actual_tools"])
            true_positive += sum((expected & actual).values())
            false_positive += sum((actual - expected).values())
            false_negative += sum((expected - actual).values())
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    )
    latencies = [turn["elapsed_ms"] for turn in turns]
    tokens = [turn["token_usage"]["total_tokens"] for turn in usage_turns]
    total_input_tokens = sum(turn["token_usage"]["input_tokens"] for turn in usage_turns)
    total_output_tokens = sum(turn["token_usage"]["output_tokens"] for turn in usage_turns)
    total_tokens = sum(tokens)
    model_calls = sum(turn["token_usage"]["model_calls"] for turn in usage_turns)
    cached_usage_missing_calls = sum(
        turn["token_usage"]["cached_usage_missing_calls"] for turn in usage_turns
    )
    cached_input_tokens = (
        sum(turn["token_usage"]["cached_input_tokens"] for turn in usage_turns)
        if cached_usage_missing_calls == 0
        else None
    )
    clarification_turns = [
        turn for turn in primary_turns if turn["expected_status"] == "needs_clarification"
    ]
    schedule_assertions = [
        assertion for turn in turns for assertion in turn.get("schedule_assertions", [])
    ]
    return {
        "cases": len(results),
        "turns": len(primary_turns),
        "continuations": len(continuation_turns),
        "exact_case_accuracy": sum(result["passed"] for result in results) / len(results),
        "status_accuracy": (
            sum(turn["status_match"] for turn in turns) / len(turns) if turns else 0
        ),
        "tool_precision": round(precision, 4),
        "tool_recall": round(recall, 4),
        "tool_f1": round(2 * precision * recall / (precision + recall), 4)
        if precision + recall
        else 0,
        "forbidden_tool_violation_rate": round(
            sum(bool(turn["forbidden_tools_used"]) for turn in turns) / len(turns) if turns else 0,
            4,
        ),
        "response_safety_violation_rate": round(
            sum(not turn["response_safety_match"] for turn in turns) / len(turns) if turns else 0,
            4,
        ),
        "token_budget_violation_rate": round(
            sum(not turn["token_budget_match"] for turn in turns) / len(turns) if turns else 0,
            4,
        ),
        "schedule_assertion_accuracy": (
            sum(assertion["passed"] for assertion in schedule_assertions) / len(schedule_assertions)
            if schedule_assertions
            else 1.0
        ),
        "clarification_accuracy": (
            sum(
                (
                    turn["clarification"]["passed"]
                    if isinstance(turn.get("clarification"), dict)
                    else turn["status_match"]
                )
                for turn in clarification_turns
            )
            / len(clarification_turns)
            if clarification_turns
            else 1.0
        ),
        "latency_ms": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
        "tokens": {
            "input": total_input_tokens,
            "output": total_output_tokens,
            "total": total_tokens,
            "mean": round(sum(tokens) / len(tokens)) if tokens else 0,
            "p50": _percentile(tokens, 0.5),
            "p95": _percentile(tokens, 0.95),
            "model_calls": model_calls,
            "cached_input": cached_input_tokens,
            "cached_usage_missing_calls": cached_usage_missing_calls,
            "prompt_cache_percent": (
                round(cached_input_tokens * 100 / total_input_tokens, 2)
                if cached_input_tokens is not None and total_input_tokens
                else None
            ),
        },
        "by_category": {
            category: _category_metrics(outcomes, category_gates.get(category))
            for category, outcomes in sorted(category_counts.items())
        },
        "stability": _stability_metrics(results),
    }


def _category_metrics(outcomes: list[bool], required_accuracy: float | None) -> dict[str, Any]:
    accuracy = sum(outcomes) / len(outcomes)
    return {
        "passed": sum(outcomes),
        "total": len(outcomes),
        "accuracy": round(accuracy, 4),
        "required_accuracy": required_accuracy,
        "gate_passed": required_accuracy is None or accuracy >= required_accuracy,
    }


def _stability_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[bool]] = {}
    for result in results:
        grouped.setdefault(result["id"], []).append(result["passed"])
    repeated = {case_id: outcomes for case_id, outcomes in grouped.items() if len(outcomes) > 1}
    return {
        "repeated_cases": len(repeated),
        "all_attempts_passed": all(all(outcomes) for outcomes in repeated.values()),
        "by_case": {
            case_id: {
                "passed": sum(outcomes),
                "attempts": len(outcomes),
                "pass_rate": round(sum(outcomes) / len(outcomes), 4),
                "all_passed": all(outcomes),
            }
            for case_id, outcomes in sorted(repeated.items())
        },
    }


async def _wait_for_terminal(
    client: httpx.AsyncClient, run_id: str, timeout: float
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(f"/api/runs/{run_id}")
        response.raise_for_status()
        run = response.json()
        if run["status"] in TERMINAL_STATUSES:
            events = await client.get(f"/api/runs/{run_id}/events")
            events.raise_for_status()
            return run, events.json()
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout:.0f}s")


async def _submit(
    client: httpx.AsyncClient, thread_id: str, message: str, operation_key: str, timeout: float
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    started = time.monotonic()
    response = await client.post(
        f"/api/threads/{thread_id}/command-runs",
        json={"message": message},
        headers={"Idempotency-Key": operation_key},
    )
    response.raise_for_status()
    run, events = await _wait_for_terminal(client, response.json()["run_id"], timeout)
    return run, events, int((time.monotonic() - started) * 1000)


async def _submit_clarification(
    client: httpx.AsyncClient,
    *,
    thread_id: str,
    state_version: int,
    option_key: str,
    operation_key: str,
    timeout: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    started = time.monotonic()
    response = await client.post(
        f"/api/threads/{thread_id}/clarification-responses",
        json={"state_version": state_version, "option_key": option_key},
        headers={"Idempotency-Key": operation_key},
    )
    response.raise_for_status()
    run, events = await _wait_for_terminal(client, response.json()["run_id"], timeout)
    return run, events, int((time.monotonic() - started) * 1000)


async def _evaluate_step(
    client: httpx.AsyncClient,
    *,
    expected: EvalTurn,
    run: dict[str, Any],
    events: list[dict[str, Any]],
    elapsed_ms: int,
    variables: dict[str, str],
) -> dict[str, Any]:
    actual_tools = _tool_counts(events)
    forbidden_used = {
        name: actual_tools[name] for name in expected.forbidden_tools if actual_tools.get(name, 0)
    }
    status_match = run["status"] == expected.expected_status
    token_usage = _token_usage(events)
    token_budget_match = (
        expected.max_total_tokens is None
        or token_usage["total_tokens"] <= expected.max_total_tokens
    )
    schedule_assertions = await evaluate_schedule_expectations(
        client,
        expected.expected_schedule,
        variables,
    )
    schedule_match = all(assertion["passed"] for assertion in schedule_assertions)
    result_message = run.get("result_message")
    normalized_result = result_message.casefold() if isinstance(result_message, str) else ""
    forbidden_response_matches = [
        render_template(value, variables)
        for value in expected.forbidden_response_substrings
        if render_template(value, variables).casefold() in normalized_result
    ]
    response_safety_match = not forbidden_response_matches
    passed = (
        status_match
        and actual_tools == expected.expected_tools
        and not forbidden_used
        and token_budget_match
        and schedule_match
        and response_safety_match
    )
    return {
        "run_id": run["id"],
        "status": run["status"],
        "expected_status": expected.expected_status,
        "status_match": status_match,
        "expected_tools": expected.expected_tools,
        "actual_tools": actual_tools,
        "forbidden_tools_used": forbidden_used,
        "max_total_tokens": expected.max_total_tokens,
        "token_budget_match": token_budget_match,
        "schedule_match": schedule_match,
        "schedule_assertions": schedule_assertions,
        "result_message": result_message,
        "forbidden_response_matches": forbidden_response_matches,
        "response_safety_match": response_safety_match,
        "elapsed_ms": elapsed_ms,
        "token_usage": token_usage,
        "passed": passed,
    }


def _clarification_resume_turn(flow: ClarificationFlowExpectation) -> EvalTurn:
    resume = flow.resume
    return EvalTurn(
        message="<clarification-response>",
        expected_tools=resume.expected_tools,
        expected_status=resume.expected_status,
        forbidden_tools=resume.forbidden_tools,
        max_total_tokens=resume.max_total_tokens,
        expected_schedule=resume.expected_schedule,
        forbidden_response_substrings=(),
    )


async def _run_clarification_flow(
    client: httpx.AsyncClient,
    *,
    thread_id: str,
    source_run_id: str,
    flow: ClarificationFlowExpectation,
    variables: dict[str, str],
    execution_id: str,
    case_id: str,
    turn_index: int,
    timeout: float,
) -> dict[str, Any]:
    inspection = await inspect_clarification(
        client,
        thread_id=thread_id,
        source_run_id=source_run_id,
        expectation=flow,
        variables=variables,
    )
    state_version = inspection.get("state_version")
    option_key = inspection.get("selected_option_key")
    if (
        not inspection["passed"]
        or not isinstance(state_version, int)
        or not isinstance(option_key, str)
    ):
        return {"passed": False, "inspection": inspection, "resume": None}

    run, events, elapsed_ms = await _submit_clarification(
        client,
        thread_id=thread_id,
        state_version=state_version,
        option_key=option_key,
        operation_key=_operation_key(execution_id, case_id, "clarification", turn_index),
        timeout=timeout,
    )
    resume = await _evaluate_step(
        client,
        expected=_clarification_resume_turn(flow),
        run=run,
        events=events,
        elapsed_ms=elapsed_ms,
        variables=variables,
    )
    interaction_consumed = await clarification_is_consumed(client, thread_id=thread_id)
    return {
        "passed": resume["passed"] and interaction_consumed,
        "inspection": inspection,
        "interaction_consumed": interaction_consumed,
        "resume": resume,
    }


async def _run_case(
    client: httpx.AsyncClient,
    case: EvalCase,
    timeout: float,
    execution_id: str,
    templates: EvalTemplateContext,
    attempt: int = 1,
) -> dict[str, Any]:
    case_execution_id = f"{case.id}:attempt-{attempt}"
    response = await client.post(
        "/api/threads",
        json={"title": f"[EVAL {execution_id[:8]}] {case.id} #{attempt}"},
    )
    response.raise_for_status()
    thread_id = response.json()["id"]
    tag = thread_id[:8]
    variables = templates.variables(tag=tag)
    setup = []
    for index, expected in enumerate(case.setup, start=1):
        run, events, elapsed_ms = await _submit(
            client,
            thread_id,
            render_template(expected.message, variables),
            _operation_key(execution_id, case_execution_id, "setup", index),
            timeout,
        )
        setup_result = await _evaluate_step(
            client,
            expected=expected,
            run=run,
            events=events,
            elapsed_ms=elapsed_ms,
            variables=variables,
        )
        setup.append(setup_result)
        if not setup_result["passed"]:
            return {
                "id": case.id,
                "attempt": attempt,
                "category": case.category,
                "category_min_accuracy": case.category_min_accuracy,
                "thread_id": thread_id,
                "passed": False,
                "setup": setup,
                "turns": [],
            }
    turns = []
    for index, expected in enumerate(case.turns, start=1):
        run, events, elapsed_ms = await _submit(
            client,
            thread_id,
            render_template(expected.message, variables),
            _operation_key(execution_id, case_execution_id, "turn", index),
            timeout,
        )
        turn_result = await _evaluate_step(
            client,
            expected=expected,
            run=run,
            events=events,
            elapsed_ms=elapsed_ms,
            variables=variables,
        )
        if expected.clarification is not None and turn_result["passed"]:
            clarification = await _run_clarification_flow(
                client,
                thread_id=thread_id,
                source_run_id=run["id"],
                flow=expected.clarification,
                variables=variables,
                execution_id=execution_id,
                case_id=case_execution_id,
                turn_index=index,
                timeout=timeout,
            )
            turn_result["clarification"] = clarification
            turn_result["passed"] = clarification["passed"]
        turns.append(turn_result)
        if not turn_result["passed"]:
            break
    return {
        "id": case.id,
        "attempt": attempt,
        "category": case.category,
        "category_min_accuracy": case.category_min_accuracy,
        "thread_id": thread_id,
        "passed": (
            all(item["passed"] for item in setup)
            and len(turns) == len(case.turns)
            and all(turn["passed"] for turn in turns)
        ),
        "setup": setup,
        "turns": turns,
    }


async def _main(args: argparse.Namespace) -> int:
    cases = load_corpus(args.corpus)
    cases = [
        case
        for case in cases
        if (not args.category or case.category in args.category)
        and (not args.case or case.id in args.case)
    ][: args.limit]
    if not 1 <= args.repeat <= 10:
        raise SystemExit("--repeat must be between 1 and 10")
    if args.repeat > 1 and not args.case:
        raise SystemExit("--repeat requires at least one explicit --case selection")
    if not args.execute:
        counts = Counter(case.category for case in cases)
        print(
            json.dumps(
                {
                    "cases": len(cases),
                    "planned_runs": len(cases) * args.repeat,
                    "repeat": args.repeat,
                    "categories": counts,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    execution_id = uuid4().hex
    templates = EvalTemplateContext.capture()
    try:
        eval_token = _resolve_eval_token(args.token_file)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if eval_token and args.login_identifier:
        raise SystemExit("Eval token authentication cannot be combined with password login")
    headers = {"Authorization": f"Bearer {eval_token}"} if eval_token else None
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout,
        headers=headers,
    ) as client:
        if args.login_identifier:
            password = os.getenv("DAYBOARD_EVAL_PASSWORD")
            if not password:
                raise SystemExit("DAYBOARD_EVAL_PASSWORD is required for authenticated Eval")
            login = await client.post(
                "/api/auth/login", json={"identifier": args.login_identifier, "password": password}
            )
            login.raise_for_status()
        results = []
        for case in cases:
            for attempt in range(1, args.repeat + 1):
                results.append(
                    await _run_case(
                        client,
                        case,
                        args.timeout,
                        execution_id,
                        templates,
                        attempt,
                    )
                )
    report = {
        "execution_id": execution_id,
        "template_context": {
            "today": templates.today,
            "tomorrow": templates.tomorrow,
            "day_after_tomorrow": templates.day_after_tomorrow,
            "future_date": templates.future_date,
        },
        "metrics": calculate_metrics(results),
        "results": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n")
    overall_passed = report["metrics"]["exact_case_accuracy"] >= args.min_accuracy
    category_gates_passed = all(
        category["gate_passed"] for category in report["metrics"]["by_category"].values()
    )
    return 0 if overall_passed and category_gates_passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the quantitative Dayboard Agent Eval corpus.")
    parser.add_argument(
        "--corpus", type=Path, default=Path(__file__).parents[2] / "evals/agent_eval.json"
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("DAYBOARD_EVAL_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--login-identifier", default=os.getenv("DAYBOARD_EVAL_IDENTIFIER"))
    parser.add_argument(
        "--token-file",
        type=Path,
        default=(
            Path(os.environ["DAYBOARD_EVAL_TOKEN_FILE"])
            if os.getenv("DAYBOARD_EVAL_TOKEN_FILE")
            else None
        ),
    )
    parser.add_argument("--category", action="append")
    parser.add_argument("--case", action="append")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat explicitly selected cases 1-10 times using isolated Threads.",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
