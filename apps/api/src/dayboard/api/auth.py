from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from dayboard.config import Settings, get_settings
from dayboard.api.errors import ApiProblem
from dayboard.api.rate_limit import limiter
from agent_platform.core import UserContext
from dayboard.db.models import (
    UserCredentialRow,
    UserProfileRow,
    UserRow,
    UserSessionRow,
)
from dayboard.db.session import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = structlog.get_logger(__name__)
password_hash = PasswordHash.recommended()
_dummy_password_hash = password_hash.hash("dayboard-invalid-password-placeholder")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    locale: str = Field(default="zh-CN", max_length=32)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class AccountResponse(BaseModel):
    user_id: str
    username: str
    email: str | None
    display_name: str | None
    timezone: str
    locale: str


def _normalized(value: str) -> str:
    return value.strip().lower()


def _token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


async def _account_for_session(
    session: AsyncSession, token: str
) -> tuple[UserSessionRow, UserRow, UserProfileRow] | None:
    now = datetime.now(timezone.utc)
    statement = (
        select(UserSessionRow, UserRow, UserProfileRow)
        .join(UserRow, UserRow.id == UserSessionRow.user_id)
        .join(UserProfileRow, UserProfileRow.user_id == UserRow.id)
        .where(
            UserSessionRow.token_hash == _token_digest(token),
            UserSessionRow.revoked_at.is_(None),
            UserSessionRow.expires_at > now,
            UserRow.is_active.is_(True),
            UserRow.deleted_at.is_(None),
        )
        .limit(1)
    )
    result = (await session.execute(statement)).one_or_none()
    return result if result is not None else None


async def _account_for_eval_identity(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> tuple[UserRow, UserProfileRow] | None:
    statement = (
        select(UserRow, UserProfileRow)
        .join(UserProfileRow, UserProfileRow.user_id == UserRow.id)
        .where(
            UserRow.id == user_id,
            UserRow.is_active.is_(True),
            UserRow.deleted_at.is_(None),
        )
        .limit(1)
    )
    result = (await session.execute(statement)).one_or_none()
    return result if result is not None else None


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization")
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise ApiProblem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTHENTICATION_REQUIRED",
            message="Authentication required",
        )
    return token.strip()


async def _eval_account_for_request(
    request: Request,
    session: AsyncSession,
    settings: Settings,
) -> tuple[UserRow, UserProfileRow] | None:
    token = _bearer_token(request)
    if token is None:
        return None
    configured_digest = (
        settings.eval_auth_token_sha256.get_secret_value().lower()
        if settings.eval_auth_token_sha256 is not None
        else ""
    )
    if (
        not configured_digest
        or settings.eval_user_id is None
        or not secrets.compare_digest(_token_digest(token), configured_digest)
    ):
        raise ApiProblem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_EVAL_TOKEN",
            message="Invalid Eval token",
        )
    account = await _account_for_eval_identity(
        session,
        user_id=settings.eval_user_id,
    )
    if account is None:
        raise ApiProblem(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_EVAL_IDENTITY",
            message="Eval identity is unavailable",
        )
    return account


async def _login_credential_snapshot(
    session: AsyncSession,
    identifier: str,
) -> tuple[UUID, str] | None:
    candidate = (
        await session.execute(
            select(UserRow.id, UserCredentialRow.password_hash)
            .join(UserCredentialRow, UserCredentialRow.user_id == UserRow.id)
            .where(
                or_(UserRow.username == identifier, UserRow.email == identifier),
                UserRow.is_active.is_(True),
                UserRow.deleted_at.is_(None),
                UserCredentialRow.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).one_or_none()
    if candidate is None:
        return None
    return candidate.id, candidate.password_hash


async def _account_for_login(
    session: AsyncSession,
    user_id: UUID,
    expected_password_hash: str,
) -> tuple[UserRow, UserCredentialRow, UserProfileRow] | None:
    locked_user_id = await session.scalar(
        select(UserRow.id)
        .where(
            UserRow.id == user_id,
            UserRow.is_active.is_(True),
            UserRow.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if locked_user_id is None:
        return None

    statement = (
        select(UserRow, UserCredentialRow, UserProfileRow)
        .join(UserCredentialRow, UserCredentialRow.user_id == UserRow.id)
        .join(UserProfileRow, UserProfileRow.user_id == UserRow.id)
        .where(
            UserRow.id == locked_user_id,
            UserCredentialRow.deleted_at.is_(None),
            UserCredentialRow.password_hash == expected_password_hash,
        )
        .limit(1)
        .with_for_update(of=UserCredentialRow)
    )
    account = (await session.execute(statement)).one_or_none()
    return account if account is not None else None


def _response(
    user: UserRow,
    profile: UserProfileRow,
    *,
    timezone: str,
) -> AccountResponse:
    return AccountResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        timezone=timezone,
        locale=profile.locale,
    )


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.auth_session_cookie_name,
        token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


async def get_user_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserContext:
    if settings.auth_mode == "development":
        context = UserContext(
            user_id=settings.default_user_id,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
    else:
        eval_account = await _eval_account_for_request(request, session, settings)
        if eval_account is not None:
            user, profile = eval_account
            authentication_kind = "eval_token"
        else:
            token = request.cookies.get(settings.auth_session_cookie_name)
            account = await _account_for_session(session, token) if token else None
            if account is None:
                raise ApiProblem(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    code="AUTHENTICATION_REQUIRED",
                    message="Authentication required",
                )
            user_session, user, profile = account
            user_session.last_seen_at = datetime.now(timezone.utc)
            await session.commit()
            authentication_kind = "session_cookie"
        context = UserContext(
            user_id=user.id,
            timezone=profile.timezone,
            locale=profile.locale,
        )
        request.state.authentication_kind = authentication_kind
    structlog.contextvars.bind_contextvars(
        user_id=str(context.user_id)
    )
    return context


@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().rate_limit_registration)
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountResponse:
    del request
    username = _normalized(body.username)
    email = _normalized(str(body.email)) if body.email else None
    user = UserRow(username=username, email=email, display_name=body.display_name)
    session.add(user)
    await session.flush()
    profile = UserProfileRow(
        user_id=user.id,
        timezone=settings.default_timezone,
        locale=body.locale,
    )
    credential = UserCredentialRow(user_id=user.id, password_hash=password_hash.hash(body.password))
    raw_token = secrets.token_urlsafe(32)
    user_session = UserSessionRow(
        user_id=user.id,
        token_hash=_token_digest(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.auth_session_ttl_seconds),
    )
    session.add_all([profile, credential, user_session])
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        logger.info("dayboard.auth.registration_rejected", reason="duplicate_identifier")
        raise ApiProblem(
            status_code=409,
            code="IDENTIFIER_ALREADY_REGISTERED",
            message="Username or email is already registered",
        ) from exc
    _set_session_cookie(response, raw_token, settings)
    logger.info("dayboard.auth.registered", user_id=str(user.id))
    return _response(user, profile, timezone=profile.timezone)


@router.post("/login", response_model=AccountResponse)
@limiter.limit(lambda: get_settings().rate_limit_login)
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountResponse:
    del request
    identifier = _normalized(body.identifier)
    candidate = await _login_credential_snapshot(session, identifier)
    candidate_hash = candidate[1] if candidate else _dummy_password_hash
    await session.rollback()
    valid = await asyncio.to_thread(password_hash.verify, body.password, candidate_hash)
    if candidate is None or not valid:
        logger.info("dayboard.auth.login_rejected", reason="invalid_credentials")
        raise ApiProblem(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid credentials",
        )
    account = await _account_for_login(session, candidate[0], candidate_hash)
    if account is None:
        await session.rollback()
        logger.info("dayboard.auth.login_rejected", reason="credential_changed")
        raise ApiProblem(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid credentials",
        )
    user, _, profile = account
    raw_token = secrets.token_urlsafe(32)
    session.add(
        UserSessionRow(
            user_id=user.id,
            token_hash=_token_digest(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=settings.auth_session_ttl_seconds),
        )
    )
    await session.commit()
    _set_session_cookie(response, raw_token, settings)
    logger.info(
        "dayboard.auth.login_succeeded", user_id=str(user.id)
    )
    return _response(user, profile, timezone=profile.timezone)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    token = request.cookies.get(settings.auth_session_cookie_name)
    if token:
        row = await session.scalar(
            select(UserSessionRow).where(UserSessionRow.token_hash == _token_digest(token))
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    logger.info("dayboard.auth.logout_completed")


@router.get("/me", response_model=AccountResponse)
async def me(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AccountResponse:
    eval_account = await _eval_account_for_request(request, session, settings)
    if eval_account is not None:
        user, profile = eval_account
        return _response(user, profile, timezone=profile.timezone)
    token = request.cookies.get(settings.auth_session_cookie_name)
    account = await _account_for_session(session, token) if token else None
    if account is None:
        raise ApiProblem(
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
            message="Authentication required",
        )
    _, user, profile = account
    return _response(user, profile, timezone=profile.timezone)
