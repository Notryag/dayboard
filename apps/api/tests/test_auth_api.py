from __future__ import annotations

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.config import Settings, get_settings
from dayboard.db.models import UserCredentialRow, UserSessionRow
from dayboard.db.session import get_session
from dayboard.main import app


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
                    "timezone": "Asia/Shanghai",
                },
            )
            assert registered.status_code == 201
            assert registered.json()["username"] == "alice.test"
            assert registered.json()["email"] == "alice@example.com"
            assert "HttpOnly" in registered.headers["set-cookie"]

            credential = await db_session.scalar(select(UserCredentialRow))
            stored_session = await db_session.scalar(select(UserSessionRow))
            assert credential is not None
            assert credential.password_hash != "correct-horse-battery-staple"
            assert stored_session is not None
            assert "dayboard_session" not in stored_session.token_hash
            assert len(stored_session.token_hash) == 64

            me = await client.get("/api/auth/me")
            assert me.status_code == 200
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
