from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any

import httpx


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "needs_clarification"}


@dataclass(frozen=True, slots=True)
class EvalTurn:
    message: str
    expected_tools: dict[str, int]
    expected_status: str
    forbidden_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    category: str
    setup: tuple[str, ...]
    turns: tuple[EvalTurn, ...]


def load_corpus(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text())
    if payload.get("version") != 1:
        raise ValueError("unsupported Agent Eval corpus version")
    cases: list[EvalCase] = []
    for category in payload.get("categories", []):
        category_name = category["name"]
        defaults = category.get("defaults", {})
        for raw_case in category.get("cases", []):
            turns = []
            for raw_turn in raw_case["turns"]:
                turn = {"message": raw_turn} if isinstance(raw_turn, str) else raw_turn
                turns.append(EvalTurn(
                    message=turn["message"],
                    expected_tools=dict(turn.get("expected_tools", defaults.get("expected_tools", {}))),
                    expected_status=turn.get(
                        "expected_status", defaults.get("expected_status", "completed")
                    ),
                    forbidden_tools=tuple(
                        turn.get("forbidden_tools", defaults.get("forbidden_tools", []))
                    ),
                ))
            cases.append(EvalCase(
                id=raw_case["id"],
                category=category_name,
                setup=tuple(raw_case.get("setup", [])),
                turns=tuple(turns),
            ))
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


def _tool_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(
        metadata["tool_name"]
        for event in events
        if event.get("event_type") == "tool_call_completed"
        and isinstance((metadata := event.get("event_metadata") or {}).get("tool_name"), str)
    ))


def _token_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
    seen_calls: set[str] = set()
    for event in events:
        if event.get("event_type") != "agent_model_completed":
            continue
        metadata = event.get("event_metadata") or {}
        call_id = metadata.get("call_id")
        if not isinstance(call_id, str) or not call_id or call_id in seen_calls:
            continue
        seen_calls.add(call_id)
        usage = metadata.get("usage") or {}
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
    return totals


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def calculate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    turns = [turn for result in results for turn in result["turns"]]
    true_positive = false_positive = false_negative = 0
    category_counts: dict[str, list[bool]] = {}
    for result in results:
        category_counts.setdefault(result["category"], []).append(result["passed"])
        for turn in result["turns"]:
            expected = Counter(turn["expected_tools"])
            actual = Counter(turn["actual_tools"])
            true_positive += sum((expected & actual).values())
            false_positive += sum((actual - expected).values())
            false_negative += sum((expected - actual).values())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    latencies = [turn["elapsed_ms"] for turn in turns]
    tokens = [turn["token_usage"]["total_tokens"] for turn in turns]
    clarification_turns = [turn for turn in turns if turn["expected_status"] == "needs_clarification"]
    return {
        "cases": len(results),
        "turns": len(turns),
        "exact_case_accuracy": sum(result["passed"] for result in results) / len(results),
        "status_accuracy": (
            sum(turn["status_match"] for turn in turns) / len(turns) if turns else 0
        ),
        "tool_precision": round(precision, 4),
        "tool_recall": round(recall, 4),
        "tool_f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0,
        "forbidden_tool_violation_rate": round(
            sum(bool(turn["forbidden_tools_used"]) for turn in turns) / len(turns) if turns else 0,
            4,
        ),
        "clarification_accuracy": (
            sum(turn["status_match"] for turn in clarification_turns) / len(clarification_turns)
            if clarification_turns else 1.0
        ),
        "latency_ms": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
        "tokens": {
            "mean": round(sum(tokens) / len(tokens)) if tokens else 0,
            "p50": _percentile(tokens, 0.5),
            "p95": _percentile(tokens, 0.95),
        },
        "by_category": {
            category: {
                "passed": sum(outcomes),
                "total": len(outcomes),
                "accuracy": round(sum(outcomes) / len(outcomes), 4),
            }
            for category, outcomes in sorted(category_counts.items())
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


async def _run_case(client: httpx.AsyncClient, case: EvalCase, timeout: float) -> dict[str, Any]:
    response = await client.post("/api/threads", json={"title": f"[EVAL] {case.id}"})
    response.raise_for_status()
    thread_id = response.json()["id"]
    tag = thread_id[:8]
    setup = []
    for index, message in enumerate(case.setup, start=1):
        run, events, elapsed_ms = await _submit(
            client,
            thread_id,
            message.format(tag=tag),
            f"eval:{case.id}:setup:{index}",
            timeout,
        )
        setup.append({
            "status": run["status"],
            "actual_tools": _tool_counts(events),
            "elapsed_ms": elapsed_ms,
            "token_usage": _token_usage(events),
            "passed": run["status"] == "completed",
        })
        if run["status"] != "completed":
            return {
                "id": case.id,
                "category": case.category,
                "thread_id": thread_id,
                "passed": False,
                "setup": setup,
                "turns": [],
            }
    turns = []
    for index, expected in enumerate(case.turns, start=1):
        run, events, elapsed_ms = await _submit(
            client, thread_id, expected.message.format(tag=tag), f"eval:{case.id}:{index}", timeout
        )
        actual_tools = _tool_counts(events)
        forbidden_used = {
            name: actual_tools[name] for name in expected.forbidden_tools if actual_tools.get(name, 0)
        }
        status_match = run["status"] == expected.expected_status
        passed = status_match and actual_tools == expected.expected_tools and not forbidden_used
        turns.append({
            "status": run["status"],
            "expected_status": expected.expected_status,
            "status_match": status_match,
            "expected_tools": expected.expected_tools,
            "actual_tools": actual_tools,
            "forbidden_tools_used": forbidden_used,
            "elapsed_ms": elapsed_ms,
            "token_usage": _token_usage(events),
            "passed": passed,
        })
        if not passed:
            break
    return {
        "id": case.id,
        "category": case.category,
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
        case for case in cases
        if (not args.category or case.category in args.category)
        and (not args.case or case.id in args.case)
    ][:args.limit]
    if not args.execute:
        counts = Counter(case.category for case in cases)
        print(json.dumps({"cases": len(cases), "categories": counts}, ensure_ascii=False, indent=2))
        return 0
    if not args.allow_writes:
        raise SystemExit("--execute requires --allow-writes because Eval creates persistent data")
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as client:
        if args.login_identifier:
            password = os.getenv("DAYBOARD_EVAL_PASSWORD")
            if not password:
                raise SystemExit("DAYBOARD_EVAL_PASSWORD is required for authenticated Eval")
            login = await client.post(
                "/api/auth/login", json={"identifier": args.login_identifier, "password": password}
            )
            login.raise_for_status()
        results = [await _run_case(client, case, args.timeout) for case in cases]
    report = {"metrics": calculate_metrics(results), "results": results}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n")
    return 0 if report["metrics"]["exact_case_accuracy"] >= args.min_accuracy else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the quantitative Dayboard Agent Eval corpus.")
    parser.add_argument("--corpus", type=Path, default=Path(__file__).parents[1] / "evals/agent_eval.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--login-identifier", default=os.getenv("DAYBOARD_EVAL_IDENTIFIER"))
    parser.add_argument("--category", action="append")
    parser.add_argument("--case", action="append")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-writes", action="store_true")
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
