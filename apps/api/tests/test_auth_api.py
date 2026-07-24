from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.config import Settings, get_settings
from dayboard.api.account_recovery import get_password_reset_mailer
from dayboard.api.routes import get_command_dispatcher
from dayboard.api.dependencies import get_command_service
from dayboard.composition.commands import build_command_service
from dayboard.db.models import (
    PasswordResetTokenRow,
    UserCredentialRow,
    UserProfileRow,
    UserSessionRow,
)
from dayboard.db.session import get_session
from dayboard.main import app


class RecordingDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[UUID] = []
        self.cancelled: list[UUID] = []

    async def enqueue(self, run_id: UUID) -> None:
        self.enqueued.append(run_id)

    async def cancel(self, run_id: UUID) -> bool:
        self.cancelled.append(run_id)
        return True


class RecordingPasswordResetMailer:
    def __init__(self) -> None:
        self.messages: list[dict[str, str | int]] = []

    async def send_password_reset(
        self,
        *,
        recipient: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None:
        self.messages.append(
            {
                "recipient": recipient,
                "reset_url": reset_url,
                "expires_minutes": expires_minutes,
            }
        )


async def test_register_login_logout_and_resolve_tenant_context(
    db_session: AsyncSession,
) -> None:
    settings = Settings(
        DAYBOARD_AUTH_MODE="password",
        DAYBOARD_AUTH_COOKIE_SECURE=False,
        DAYBOARD_RATE_LIMIT_ENABLED=False,
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            registered = await client.post(
                "/api/auth/register",
                json={
                    "username": "Alice.Test",
                    "password": "correct-horse-battery-staple",
                    "email": "ALICE@example.com",
                    "timezone": "America/New_York",
                },
            )
            assert registered.status_code == 201
            assert registered.json()["username"] == "alice.test"
            assert registered.json()["email"] == "alice@example.com"
            assert registered.json()["timezone"] == "Asia/Shanghai"
            assert "HttpOnly" in registered.headers["set-cookie"]

            credential = await db_session.scalar(select(UserCredentialRow))
            stored_session = await db_session.scalar(select(UserSessionRow))
            profile = await db_session.scalar(select(UserProfileRow))
            assert credential is not None
            assert credential.password_hash != "correct-horse-battery-staple"
            assert stored_session is not None
            assert "dayboard_session" not in stored_session.token_hash
            assert len(stored_session.token_hash) == 64
            assert profile is not None
            assert profile.timezone == "Asia/Shanghai"

            me = await client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json()["timezone"] == "Asia/Shanghai"
            owned_thread = await client.post("/api/threads", json={"title": "Private"})
            assert owned_thread.status_code == 201

            logged_out = await client.post("/api/auth/logout")
            assert logged_out.status_code == 204
            assert (await client.get("/api/auth/me")).status_code == 401

            rejected = await client.post(
                "/api/auth/login",
                json={"identifier": "alice.test", "password": "wrong"},
            )
            assert rejected.status_code == 401
            logged_in = await client.post(
                "/api/auth/login",
                json={
                    "identifier": "ALICE@EXAMPLE.COM",
                    "password": "correct-horse-battery-staple",
                },
            )
            assert logged_in.status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_request_id_is_returned_and_invalid_input_is_replaced() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        accepted = await client.get("/openapi.json", headers={"X-Request-ID": "support-123"})
        generated = await client.get("/openapi.json", headers={"X-Request-ID": "bad request id"})

    assert accepted.headers["x-request-id"] == "support-123"
    assert generated.headers["x-request-id"].startswith("req_")
    assert generated.headers["x-request-id"] != "bad request id"


async def test_password_reset_is_private_single_use_and_revokes_sessions(
    db_session: AsyncSession,
) -> None:
    settings = Settings(
        DAYBOARD_AUTH_MODE="password",
        DAYBOARD_RATE_LIMIT_ENABLED=False,
        DAYBOARD_PUBLIC_WEB_URL="https://example.com/dayboard",
        DAYBOARD_SMTP_HOST="smtp.example.com",
        DAYBOARD_MAIL_FROM_ADDRESS="no-reply@example.com",
    )
    mailer = RecordingPasswordResetMailer()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_password_reset_mailer] = lambda: mailer
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            capabilities = await client.get("/api/auth/capabilities")
            assert capabilities.json() == {"password_reset_available": True}
            registered = await client.post(
                "/api/auth/register",
                json={
                    "username": "password-reset-user",
                    "password": "original-password-123",
                    "email": "RESET@example.com",
                },
            )
            assert registered.status_code == 201

            unknown = await client.post(
                "/api/auth/password-reset/request",
                json={"email": "unknown@example.com"},
            )
            requested = await client.post(
                "/api/auth/password-reset/request",
                json={"email": "RESET@example.com"},
            )
            assert unknown.status_code == requested.status_code == 202
            assert unknown.json() == requested.json()
            assert len(mailer.messages) == 1

            reset_url = str(mailer.messages[0]["reset_url"])
            raw_token = parse_qs(urlparse(reset_url).query)["reset_token"][0]
            token_row = await db_session.scalar(select(PasswordResetTokenRow))
            assert token_row is not None
            assert token_row.token_hash != raw_token
            assert len(token_row.token_hash) == 64

            changed = await client.post(
                "/api/auth/password-reset/confirm",
                json={"token": raw_token, "password": "replacement-password-456"},
            )
            assert changed.status_code == 204
            assert all(
                row.revoked_at is not None
                for row in (await db_session.scalars(select(UserSessionRow))).all()
            )

            reused = await client.post(
                "/api/auth/password-reset/confirm",
                json={"token": raw_token, "password": "another-password-789"},
            )
            assert reused.status_code == 400
            assert reused.json()["error"]["code"] == "PASSWORD_RESET_TOKEN_INVALID"

            old_login = await client.post(
                "/api/auth/login",
                json={"identifier": "reset@example.com", "password": "original-password-123"},
            )
            assert old_login.status_code == 401
            new_login = await client.post(
                "/api/auth/login",
                json={
                    "identifier": "reset@example.com",
                    "password": "replacement-password-456",
                },
            )
            assert new_login.status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_password_reset_reports_globally_unavailable_mail(
    db_session: AsyncSession,
) -> None:
    settings = Settings(DAYBOARD_AUTH_MODE="password", DAYBOARD_RATE_LIMIT_ENABLED=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            capabilities = await client.get("/api/auth/capabilities")
            assert capabilities.json() == {"password_reset_available": False}
            response = await client.post(
                "/api/auth/password-reset/request",
                json={"email": "anyone@example.com"},
            )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "PASSWORD_RESET_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


async def test_password_sessions_cannot_read_another_users_thread(
    db_session: AsyncSession,
) -> None:
    settings = Settings(DAYBOARD_AUTH_MODE="password", DAYBOARD_RATE_LIMIT_ENABLED=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test") as alice,
            AsyncClient(transport=transport, base_url="http://test") as bob,
        ):
            assert (
                await alice.post(
                    "/api/auth/register",
                    json={"username": "alice-isolation", "password": "alice-password-123"},
                )
            ).status_code == 201
            thread = await alice.post("/api/threads", json={"title": "Alice only"})
            assert thread.status_code == 201

            assert (
                await bob.post(
                    "/api/auth/register",
                    json={"username": "bob-isolation", "password": "bob-password-12345"},
                )
            ).status_code == 201
            hidden = await bob.get(f"/api/threads/{thread.json()['id']}/messages")
            assert hidden.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_password_sessions_isolate_run_status_events_stream_and_cancel(
    db_session: AsyncSession,
) -> None:
    settings = Settings(DAYBOARD_AUTH_MODE="password", DAYBOARD_RATE_LIMIT_ENABLED=False)
    dispatcher = RecordingDispatcher()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_command_service] = lambda: build_command_service(db_session)
    app.dependency_overrides[get_command_dispatcher] = lambda: dispatcher
    from north.runtime import MemoryStreamBridge
    from dayboard.api.routes import get_stream_bridge

    app.dependency_overrides[get_stream_bridge] = MemoryStreamBridge
    try:
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://test") as alice,
            AsyncClient(transport=transport, base_url="http://test") as bob,
        ):
            assert (
                await alice.post(
                    "/api/auth/register",
                    json={"username": "alice-run", "password": "alice-run-password"},
                )
            ).status_code == 201
            created = await alice.post(
                "/api/command-runs",
                json={"message": "安排明天八点的会议"},
            )
            assert created.status_code == 202
            run_id = created.json()["run_id"]
            assert dispatcher.enqueued == [UUID(run_id)]
            assert (await alice.get(f"/api/runs/{run_id}")).status_code == 200
            assert (await alice.get(f"/api/runs/{run_id}/events")).status_code == 200

            assert (
                await bob.post(
                    "/api/auth/register",
                    json={"username": "bob-run", "password": "bob-run-password-12"},
                )
            ).status_code == 201
            assert (await bob.get(f"/api/runs/{run_id}")).status_code == 404
            assert (await bob.get(f"/api/runs/{run_id}/events")).status_code == 404
            assert (await bob.get(f"/api/runs/{run_id}/events/stream")).status_code == 404
            assert (await bob.post(f"/api/runs/{run_id}/cancel")).status_code == 404
            assert dispatcher.cancelled == []
    finally:
        app.dependency_overrides.clear()
