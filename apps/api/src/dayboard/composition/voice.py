"""Composition root for Dayboard Voice services."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.voice import VoiceTranscriptionService
from dayboard.db.voice_uow import SqlAlchemyVoiceUnitOfWork


@dataclass(frozen=True, slots=True)
class VoiceServiceScope:
    unit_of_work: SqlAlchemyVoiceUnitOfWork
    transcriptions: VoiceTranscriptionService


def build_voice_services(session: AsyncSession) -> VoiceServiceScope:
    unit_of_work = SqlAlchemyVoiceUnitOfWork(session)
    return VoiceServiceScope(
        unit_of_work=unit_of_work,
        transcriptions=VoiceTranscriptionService(unit_of_work),
    )
