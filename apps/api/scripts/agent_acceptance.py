from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
import json
import time
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class Turn:
    message: str
    expected_tools: dict[str, int] = field(default_factory=dict)
    expected_status: str = "completed"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    description: str
    turns: tuple[Turn, ...]


SCENARIOS = (
    Scenario(
        name="multi-create",
        description="Create distinct calendar and task objects from one command.",
        turns=(
            Turn(
                "明天上午 9 点创建标题为「验收{tag}项目晨会」的日程，并创建标题为「验收{tag}提交验收报告」、后天下午 6 点截止的任务",
                {"create_calendar_entry": 1, "create_task_item": 1},
            ),
        ),
    ),
    Scenario(
        name="calendar-mutations",
        description="Create two entries, then move one and cancel the other in one Run.",
        turns=(
            Turn(
                "创建两个日程，标题分别为「验收{tag}需求评审」和「验收{tag}客户访谈」，时间分别是明天上午 10 点和明天下午 3 点",
                {"create_calendar_entry": 2},
            ),
            Turn(
                "把「验收{tag}需求评审」改到后天上午 11 点，并取消「验收{tag}客户访谈」",
                {
                    "search_calendar_entries": 2,
                    "reschedule_calendar_entry": 1,
                    "cancel_calendar_entry": 1,
                },
            ),
        ),
    ),
    Scenario(
        name="task-mutations",
        description="Create two tasks, then complete one and move the other in one Run.",
        turns=(
            Turn(
                "创建两个任务，标题分别为「验收{tag}整理周报」和「验收{tag}提交报销」",
                {"create_task_item": 2},
            ),
            Turn(
                "完成「验收{tag}整理周报」，并把「验收{tag}提交报销」的截止时间改到后天下午 5 点",
                {"search_task_items": 2, "update_task_item": 2},
            ),
        ),
    ),
    Scenario(
        name="missing-target",
        description="Do not create a replacement when a mutation target does not exist.",
        turns=(
            Turn(
                "把「验收{tag}完全不存在的会议」改到后天上午 9 点",
                {"search_calendar_entries": 1},
            ),
        ),
    ),
)


async def _wait_for_terminal(
    client: httpx.AsyncClient,
    run_id: str,
    *,
    timeout: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run_response = await client.get(f"/api/runs/{run_id}")
        run_response.raise_for_status()
        run = run_response.json()
        if run["status"] in {"completed", "failed", "cancelled", "needs_clarification"}:
            events_response = await client.get(f"/api/runs/{run_id}/events")
            events_response.raise_for_status()
            return run, events_response.json()
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout:.0f}s")


def _tool_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if event.get("event_type") != "tool_call_completed":
            continue
        tool_name = (event.get("event_metadata") or {}).get("tool_name")
        if isinstance(tool_name, str):
            counts[tool_name] = counts.get(tool_name, 0) + 1
    return counts


def _token_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
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


async def _run_scenario(
    client: httpx.AsyncClient,
    scenario: Scenario,
    *,
    timeout: float,
) -> dict[str, Any]:
    thread_response = await client.post(
        "/api/threads",
        json={"title": f"[ACCEPTANCE] {scenario.name}"},
    )
    thread_response.raise_for_status()
    thread_id = thread_response.json()["id"]
    tag = thread_id[:8]
    turns = []
    passed = True
    for index, turn in enumerate(scenario.turns, start=1):
        started_at = time.monotonic()
        response = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            json={"message": turn.message.format(tag=tag)},
            headers={"Idempotency-Key": f"acceptance:{scenario.name}:{thread_id}:{index}"},
        )
        response.raise_for_status()
        run_id = response.json()["run_id"]
        run, events = await _wait_for_terminal(client, run_id, timeout=timeout)
        actual_tools = _tool_counts(events)
        missing_tools = {
            name: expected - actual_tools.get(name, 0)
            for name, expected in turn.expected_tools.items()
            if actual_tools.get(name, 0) < expected
        }
        turn_passed = run["status"] == turn.expected_status and not missing_tools
        passed = passed and turn_passed
        turns.append(
            {
                "run_id": run_id,
                "status": run["status"],
                "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                "expected_tools": turn.expected_tools,
                "actual_tools": actual_tools,
                "token_usage": _token_usage(events),
                "missing_tools": missing_tools,
                "passed": turn_passed,
                "result": run.get("result_message"),
            }
        )
        if not turn_passed:
            break
    return {
        "scenario": scenario.name,
        "thread_id": thread_id,
        "passed": passed,
        "turns": turns,
        "skipped_turns": len(scenario.turns) - len(turns),
    }


async def _main(args: argparse.Namespace) -> int:
    selected = [scenario for scenario in SCENARIOS if not args.scenario or scenario.name in args.scenario]
    if not args.execute:
        for scenario in selected:
            print(f"{scenario.name}: {scenario.description}")
        return 0
    if not args.allow_writes:
        raise SystemExit("--execute requires --allow-writes because scenarios create persistent data")
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as client:
        results = [
            await _run_scenario(client, scenario, timeout=args.timeout)
            for scenario in selected
        ]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result["passed"] for result in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run explicit Dayboard live Agent acceptance scenarios.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--scenario", action="append", choices=[item.name for item in SCENARIOS])
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-writes", action="store_true")
    raise SystemExit(asyncio.run(_main(parser.parse_args())))


if __name__ == "__main__":
    main()
