"""Composition root for independent provider usage transactions."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.provider_usage import ProviderUsageService
from dayboard.app.provider_usage_ports import (
    ProviderUsageUnitOfWork,
    ProviderUsageUnitOfWorkFactory,
)
from dayboard.db.provider_usage_uow import SqlAlchemyProviderUsageUnitOfWork
from dayboard.db.session import SessionLocal


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def build_provider_usage_unit_of_work_factory(
    session_factory: SessionFactory = SessionLocal,
) -> ProviderUsageUnitOfWorkFactory:
    @asynccontextmanager
    async def create_unit_of_work() -> AsyncIterator[ProviderUsageUnitOfWork]:
        async with session_factory() as session:
            yield SqlAlchemyProviderUsageUnitOfWork(session)

    return create_unit_of_work


def build_provider_usage_service(
    session_factory: SessionFactory = SessionLocal,
) -> ProviderUsageService:
    return ProviderUsageService(build_provider_usage_unit_of_work_factory(session_factory))
