from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.db.session import SessionLocal


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.commit()
        yield session
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.commit()
