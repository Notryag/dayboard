from __future__ import annotations

import asyncio


class FakeRunExecutor:
    """Unit-test adapter for legacy-shaped deterministic invocation fakes."""

    def __init__(self, invoker) -> None:
        self._invoker = invoker

    async def execute(self, record, **kwargs):
        del record
        hooks = kwargs.pop("lifecycle_hooks")
        observer = kwargs.pop("stream_observer", None)
        kwargs.pop("stream_modes", None)
        kwargs.pop("publish_modes", None)
        if observer is not None:
            kwargs["stream_sink"] = observer
        try:
            result = await self._invoker(**kwargs)
            if hooks.on_completed is not None:
                await hooks.on_completed(result)
            return result
        except asyncio.CancelledError:
            if hooks.on_interrupted is not None:
                await hooks.on_interrupted()
            raise
        except Exception as exc:
            if hooks.on_error is not None:
                await hooks.on_error(exc)
            raise


def fake_executor_factory(invoker):
    return lambda bridge, run_manager: FakeRunExecutor(invoker)
