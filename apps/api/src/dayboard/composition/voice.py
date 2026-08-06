"""Composition root for Dayboard Voice services."""

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.voice import VoiceTranscriptionService
from dayboard.db.voice_uow import SqlAlchemyVoiceUnitOfWork


def build_voice_service(session: AsyncSession) -> VoiceTranscriptionService:
    unit_of_work = SqlAlchemyVoiceUnitOfWork(session)
    return VoiceTranscriptionService(unit_of_work)
