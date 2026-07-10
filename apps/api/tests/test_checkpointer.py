from __future__ import annotations

import os

from north import CheckpointerConfig, make_checkpointer


async def test_postgres_checkpointer_initializes_against_test_database() -> None:
    connection_string = os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )

    async with make_checkpointer(
        CheckpointerConfig(backend="postgres", connection_string=connection_string)
    ) as saver:
        assert type(saver).__name__ == "AsyncPostgresSaver"
