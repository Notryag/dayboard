"""Composition root for Dayboard account recovery services."""

from dataclasses import dataclass

from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.account_recovery import AccountRecoveryService
from dayboard.db.account_recovery_uow import SqlAlchemyAccountRecoveryUnitOfWork


@dataclass(frozen=True, slots=True)
class AccountRecoveryServiceScope:
    unit_of_work: SqlAlchemyAccountRecoveryUnitOfWork
    recovery: AccountRecoveryService


def build_account_recovery_services(session: AsyncSession) -> AccountRecoveryServiceScope:
    unit_of_work = SqlAlchemyAccountRecoveryUnitOfWork(session)
    return AccountRecoveryServiceScope(
        unit_of_work=unit_of_work,
        recovery=AccountRecoveryService(unit_of_work, PasswordHash.recommended()),
    )
