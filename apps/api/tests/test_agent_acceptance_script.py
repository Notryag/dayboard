from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace

import pytest


_script_path = Path(__file__).parents[1] / "scripts" / "agent_acceptance.py"
_script_spec = importlib.util.spec_from_file_location("dayboard_agent_acceptance_test", _script_path)
assert _script_spec and _script_spec.loader
agent_acceptance = importlib.util.module_from_spec(_script_spec)
sys.modules[_script_spec.name] = agent_acceptance
_script_spec.loader.exec_module(agent_acceptance)


class FakeResponse:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def json(self) -> object:
        return self.body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP status {self.status_code}")


class FakeAcceptanceClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.calls: list[tuple[str, str, object]] = []

    async def __aenter__(self) -> FakeAcceptanceClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, path: str, *, json: object, headers: object = None) -> FakeResponse:
        self.calls.append(("POST", path, json))
        if path == "/api/auth/login":
            assert json == {"identifier": "acceptance-user", "password": "secret-value"}
            return FakeResponse({"username": "acceptance-user"})
        if path == "/api/threads":
            return FakeResponse({"id": "thread12345678"})
        if path.endswith("/command-runs"):
            return FakeResponse({"run_id": "run-1"})
        raise AssertionError(f"unexpected POST {path}")

    async def get(self, path: str) -> FakeResponse:
        self.calls.append(("GET", path, None))
        if path == "/api/runs/run-1":
            return FakeResponse(
                {"status": "completed", "result_message": "没有找到需要修改的日程。"}
            )
        if path == "/api/runs/run-1/events":
            return FakeResponse(
                [
                    {
                        "event_type": "tool_call_completed",
                        "event_metadata": {"tool_name": "search_calendar_entries"},
                    }
                ]
            )
        raise AssertionError(f"unexpected GET {path}")


@pytest.mark.asyncio
async def test_authenticated_acceptance_logs_in_before_running_scenario(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clients: list[FakeAcceptanceClient] = []

    def build_client(*args: object, **kwargs: object) -> FakeAcceptanceClient:
        client = FakeAcceptanceClient(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(agent_acceptance.httpx, "AsyncClient", build_client)
    monkeypatch.setenv("DAYBOARD_ACCEPTANCE_PASSWORD", "secret-value")
    args = SimpleNamespace(
        allow_writes=True,
        base_url="https://dayboard.example.test",
        execute=True,
        login_identifier="acceptance-user",
        scenario=["missing-target"],
        timeout=1.0,
    )

    result = await agent_acceptance._main(args)

    assert result == 0
    assert clients[0].calls[0][1] == "/api/auth/login"
    assert "secret-value" not in capsys.readouterr().out
