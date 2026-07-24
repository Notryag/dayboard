from __future__ import annotations

from types import SimpleNamespace

from north.runtime import MemoryStreamBridge

from dayboard.composition.platform import build_platform_unit_of_work_factory
from dayboard.composition.runs import build_run_execution_scope
from dayboard.config import Settings


class FakeSessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        del exc_type, exc, traceback
        return False


async def test_platform_unit_of_work_factory_opens_a_fresh_session_each_time() -> None:
    sessions: list[object] = []

    def session_factory() -> FakeSessionContext:
        session = SimpleNamespace()
        sessions.append(session)
        return FakeSessionContext(session)

    factory = build_platform_unit_of_work_factory(session_factory)
    async with factory() as first:
        async with factory() as second:
            assert first is not second

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]


def test_run_execution_scope_creates_one_driver_per_run() -> None:
    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
    )
    session = SimpleNamespace()

    first = build_run_execution_scope(
        session,
        settings=settings,
        stream_bridge=MemoryStreamBridge(),
    )
    second = build_run_execution_scope(
        session,
        settings=settings,
        stream_bridge=MemoryStreamBridge(),
    )

    assert first is not second
    assert first.driver is not second.driver
