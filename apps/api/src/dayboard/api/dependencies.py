"""FastAPI-only dependency composition."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.commands import CommandService
from dayboard.composition.commands import build_command_service
from dayboard.db.session import get_session


def get_command_service(session: AsyncSession = Depends(get_session)) -> CommandService:
    return build_command_service(session)
