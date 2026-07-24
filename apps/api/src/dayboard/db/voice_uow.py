"""SQLAlchemy transaction boundary for Voice transcription use cases."""

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.db.voice_repositories import VoiceTranscriptRepository


class SqlAlchemyVoiceUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transcripts = VoiceTranscriptRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
