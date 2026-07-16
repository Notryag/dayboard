from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

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
from dayboard.context import TenantContext
from dayboard.db.models import (
    TenantMembershipRow,
    TenantRow,
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
    tenant_id: str
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
) -> tuple[UserSessionRow, UserRow, TenantMembershipRow, UserProfileRow] | None:
    now = datetime.now(timezone.utc)
    statement = (
        select(UserSessionRow, UserRow, TenantMembershipRow, UserProfileRow)
        .join(UserRow, UserRow.id == UserSessionRow.user_id)
        .join(
            TenantMembershipRow,
            (TenantMembershipRow.user_id == UserRow.id)
            & (TenantMembershipRow.status == "active")
            & (TenantMembershipRow.deleted_at.is_(None)),
        )
        .join(UserProfileRow, UserProfileRow.user_id == UserRow.id)
        .where(
            UserSessionRow.token_hash == _token_digest(token),
            UserSessionRow.revoked_at.is_(None),
            UserSessionRow.expires_at > now,
            UserRow.is_active.is_(True),
            UserRow.deleted_at.is_(None),
        )
        .order_by(TenantMembershipRow.created_at)
        .limit(1)
    )
    result = (await session.execute(statement)).one_or_none()
    return result if result is not None else None


def _response(
    user: UserRow,
    membership: TenantMembershipRow,
    profile: UserProfileRow,
    *,
    timezone: str,
) -> AccountResponse:
    return AccountResponse(
        user_id=str(user.id),
        tenant_id=str(membership.tenant_id),
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


async def get_tenant_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TenantContext:
    if settings.auth_mode == "development":
        context = TenantContext(
            tenant_id=settings.default_tenant_id,
            user_id=settings.default_user_id,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
    else:
        token = request.cookies.get(settings.auth_session_cookie_name)
        account = await _account_for_session(session, token) if token else None
        if account is None:
            raise ApiProblem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="AUTHENTICATION_REQUIRED",
                message="Authentication required",
            )
        user_session, user, membership, profile = account
        user_session.last_seen_at = datetime.now(timezone.utc)
        await session.commit()
        context = TenantContext(
            tenant_id=membership.tenant_id,
            user_id=user.id,
            timezone=settings.default_timezone,
            locale=profile.locale,
        )
    structlog.contextvars.bind_contextvars(
        tenant_id=str(context.tenant_id), user_id=str(context.user_id)
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
    tenant = TenantRow(name=body.display_name or username)
    session.add_all([user, tenant])
    await session.flush()
    profile = UserProfileRow(
        user_id=user.id,
        timezone=settings.default_timezone,
        locale=body.locale,
    )
    membership = TenantMembershipRow(tenant_id=tenant.id, user_id=user.id, role="owner")
    credential = UserCredentialRow(user_id=user.id, password_hash=password_hash.hash(body.password))
    raw_token = secrets.token_urlsafe(32)
    user_session = UserSessionRow(
        user_id=user.id,
        token_hash=_token_digest(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.auth_session_ttl_seconds),
    )
    session.add_all([profile, membership, credential, user_session])
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
    logger.info("dayboard.auth.registered", user_id=str(user.id), tenant_id=str(tenant.id))
    return _response(user, membership, profile, timezone=settings.default_timezone)


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
    statement = (
        select(UserRow, UserCredentialRow, TenantMembershipRow, UserProfileRow)
        .join(UserCredentialRow, UserCredentialRow.user_id == UserRow.id)
        .join(TenantMembershipRow, TenantMembershipRow.user_id == UserRow.id)
        .join(UserProfileRow, UserProfileRow.user_id == UserRow.id)
        .where(
            or_(UserRow.username == identifier, UserRow.email == identifier),
            UserRow.is_active.is_(True),
            UserRow.deleted_at.is_(None),
            TenantMembershipRow.status == "active",
            TenantMembershipRow.deleted_at.is_(None),
        )
        .order_by(TenantMembershipRow.created_at)
        .limit(1)
    )
    account = (await session.execute(statement)).one_or_none()
    candidate_hash = account[1].password_hash if account else _dummy_password_hash
    valid = password_hash.verify(body.password, candidate_hash)
    if account is None or not valid:
        logger.info("dayboard.auth.login_rejected", reason="invalid_credentials")
        raise ApiProblem(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid credentials",
        )
    user, _, membership, profile = account
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
        "dayboard.auth.login_succeeded", user_id=str(user.id), tenant_id=str(membership.tenant_id)
    )
    return _response(user, membership, profile, timezone=settings.default_timezone)


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
    token = request.cookies.get(settings.auth_session_cookie_name)
    account = await _account_for_session(session, token) if token else None
    if account is None:
        raise ApiProblem(
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
            message="Authentication required",
        )
    _, user, membership, profile = account
    return _response(user, membership, profile, timezone=settings.default_timezone)
