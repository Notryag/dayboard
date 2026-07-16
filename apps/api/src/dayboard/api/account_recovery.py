from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from dayboard.api.errors import ApiProblem
from dayboard.api.rate_limit import limiter
from dayboard.app.account_recovery import AccountRecoveryService
from dayboard.config import Settings, get_settings
from dayboard.db.session import get_session
from dayboard.integrations.email import PasswordResetMailer, SmtpPasswordResetMailer


router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = structlog.get_logger(__name__)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=10, max_length=128)


class PasswordResetRequestResponse(BaseModel):
    message: str


class AuthCapabilitiesResponse(BaseModel):
    password_reset_available: bool


def get_password_reset_mailer(
    settings: Settings = Depends(get_settings),
) -> PasswordResetMailer | None:
    if not settings.password_reset_mail_enabled:
        return None
    smtp_password = (
        settings.smtp_password.get_secret_value() if settings.smtp_password is not None else None
    )
    return SmtpPasswordResetMailer(
        host=settings.smtp_host or "",
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=smtp_password,
        security=settings.smtp_security,
        from_address=settings.mail_from_address or "",
        from_name=settings.mail_from_name,
    )


async def _deliver_password_reset(
    mailer: PasswordResetMailer,
    *,
    recipient: str,
    reset_url: str,
    expires_minutes: int,
    user_id: str,
) -> None:
    try:
        await mailer.send_password_reset(
            recipient=recipient,
            reset_url=reset_url,
            expires_minutes=expires_minutes,
        )
        logger.info("dayboard.auth.password_reset_delivered", user_id=user_id)
    except Exception as exc:
        logger.error(
            "dayboard.auth.password_reset_delivery_failed",
            user_id=user_id,
            error_type=type(exc).__name__,
        )


@router.get("/capabilities", response_model=AuthCapabilitiesResponse)
async def auth_capabilities(
    settings: Settings = Depends(get_settings),
) -> AuthCapabilitiesResponse:
    return AuthCapabilitiesResponse(password_reset_available=settings.password_reset_mail_enabled)


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: get_settings().rate_limit_password_reset_request)
async def request_password_reset(
    request: Request,
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    mailer: PasswordResetMailer | None = Depends(get_password_reset_mailer),
) -> PasswordResetRequestResponse:
    del request
    generic = PasswordResetRequestResponse(
        message="If the account exists, a password reset email has been sent"
    )
    if mailer is None:
        logger.warning("dayboard.auth.password_reset_mail_unavailable")
        raise ApiProblem(
            status_code=503,
            code="PASSWORD_RESET_UNAVAILABLE",
            message="Password reset email is not configured",
        )

    issued = await AccountRecoveryService(session).issue_token(
        str(body.email).strip().lower(),
        ttl_seconds=settings.password_reset_ttl_seconds,
    )
    if issued is None:
        logger.info("dayboard.auth.password_reset_requested", account_found=False)
        return generic

    reset_url = f"{settings.public_web_url}/?reset_token={quote(issued.raw_token, safe='')}"
    background_tasks.add_task(
        _deliver_password_reset,
        mailer,
        recipient=issued.recipient,
        reset_url=reset_url,
        expires_minutes=max(1, settings.password_reset_ttl_seconds // 60),
        user_id=issued.user_id,
    )
    logger.info(
        "dayboard.auth.password_reset_requested",
        account_found=True,
        user_id=issued.user_id,
    )
    return generic


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_password_reset)
async def confirm_password_reset(
    request: Request,
    body: PasswordResetConfirmRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    del request
    changed = await AccountRecoveryService(session).reset_password(body.token, body.password)
    if not changed:
        raise ApiProblem(
            status_code=400,
            code="PASSWORD_RESET_TOKEN_INVALID",
            message="Password reset link is invalid or expired",
        )
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    logger.info("dayboard.auth.password_reset_completed")
