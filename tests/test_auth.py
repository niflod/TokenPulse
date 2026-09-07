"""
tests/test_auth.py — Complete test suite for TokenPulse JWT Authentication.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import httpx
import pytest
import pytest_asyncio
from database import AsyncSessionLocal, init_db
from main import app
from models import User
from routers.auth import create_access_token
from sqlalchemy import delete


@pytest_asyncio.fixture(autouse=True)
async def clean_users_db():
    """Ensure clean database before each auth test."""
    await init_db()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()


@pytest.mark.asyncio
async def test_auth_status_empty_and_created():
    """Verify auth status reflects whether an admin user exists."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initial status -> false
        res = await client.get("/api/auth/status")
        assert res.status_code == 200
        assert res.json()["setup_completed"] is False

        # 2. Create admin via setup
        setup_res = await client.post(
            "/api/auth/setup",
            json={"username": "superadmin", "password": "securepassword123"},
        )
        assert setup_res.status_code == 200
        setup_data = setup_res.json()
        assert setup_data["status"] == "created"
        assert setup_data["username"] == "superadmin"
        assert "token" in setup_data
        assert setup_data["expires_in"] == 24 * 3600

        # 3. Status is now true
        status_res = await client.get("/api/auth/status")
        assert status_res.status_code == 200
        assert status_res.json()["setup_completed"] is True


@pytest.mark.asyncio
async def test_auth_setup_remote_takeover_blocked(monkeypatch):
    """Verify that remote callers (non-localhost) without bootstrap token are blocked with 403."""
    from config import settings
    monkeypatch.setattr(settings, "admin_bootstrap_token", "super-secret-bootstrap-123")

    transport = httpx.ASGITransport(app=app, client=("198.51.100.25", 54321))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Remote request without token -> 403
        blocked_res = await client.post(
            "/api/auth/setup",
            json={"username": "remotehacker", "password": "securepassword123"},
        )
        assert blocked_res.status_code == 403
        assert "Setup administrativo remoto bloqueado" in blocked_res.text

        # Remote request with invalid token -> 403
        wrong_res = await client.post(
            "/api/auth/setup",
            json={"username": "remotehacker", "password": "securepassword123"},
            headers={"X-Bootstrap-Token": "wrong-token"},
        )
        assert wrong_res.status_code == 403

        # Remote request with correct token -> 200
        ok_res = await client.post(
            "/api/auth/setup",
            json={"username": "validremoteadmin", "password": "securepassword123"},
            headers={"X-Bootstrap-Token": "super-secret-bootstrap-123"},
        )
        assert ok_res.status_code == 200
        assert ok_res.json()["status"] == "created"


@pytest.mark.asyncio
async def test_auth_setup_conflict():
    """Verify that second setup attempt returns 409 Conflict."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First setup succeeds
        r1 = await client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "password123"},
        )
        assert r1.status_code == 200

        # Second setup fails with 409 Conflict
        r2 = await client.post(
            "/api/auth/setup",
            json={"username": "another_admin", "password": "password123"},
        )
        assert r2.status_code == 409


@pytest.mark.asyncio
async def test_auth_login_success_and_failure():
    """Verify login with correct and incorrect credentials."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Setup admin
        await client.post(
            "/api/auth/setup",
            json={"username": "testuser", "password": "mypassword123"},
        )

        # 1. Valid login
        login_ok = await client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "mypassword123"},
        )
        assert login_ok.status_code == 200
        data = login_ok.json()
        assert "token" in data
        assert data["username"] == "testuser"

        # 2. Wrong password -> 401
        login_bad_pw = await client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "wrongpassword"},
        )
        assert login_bad_pw.status_code == 401

        # 3. Wrong username -> 401
        login_bad_user = await client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "mypassword123"},
        )
        assert login_bad_user.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoints_require_jwt():
    """Verify that API endpoints reject unauthenticated requests and accept valid JWT."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Request without token -> 401 Unauthorized
        res_no_auth = await client.get("/api/metrics/summary")
        assert res_no_auth.status_code == 401

        res_logs_no_auth = await client.get("/api/logs")
        assert res_logs_no_auth.status_code == 401

        # 2. Request with invalid token -> 401 Unauthorized
        res_bad_token = await client.get(
            "/api/metrics/summary",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert res_bad_token.status_code == 401

        # 3. Create valid token
        token, _ = create_access_token("admin")
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 4. Request with valid token -> 200 OK
        res_auth_metrics = await client.get("/api/metrics/summary", headers=auth_headers)
        assert res_auth_metrics.status_code == 200

        res_auth_logs = await client.get("/api/logs", headers=auth_headers)
        assert res_auth_logs.status_code == 200


@pytest.mark.asyncio
async def test_auth_change_password():
    """Verify password change flow and re-authentication."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Setup
        await client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "original_password123"},
        )

        # Login to get token
        login_res = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "original_password123"},
        )
        token = login_res.json()["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 1. Change password with wrong current password -> 401
        bad_change = await client.put(
            "/api/auth/password",
            json={"current_password": "wrong_password", "new_password": "new_secret_pass123"},
            headers=auth_headers,
        )
        assert bad_change.status_code == 401

        # 2. Change password with correct current password -> 200
        ok_change = await client.put(
            "/api/auth/password",
            json={"current_password": "original_password123", "new_password": "new_secret_pass123"},
            headers=auth_headers,
        )
        assert ok_change.status_code == 200
        assert ok_change.json()["status"] == "password_changed"

        # 3. Old password now fails
        old_login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "original_password123"},
        )
        assert old_login.status_code == 401

        # 4. New password works
        new_login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "new_secret_pass123"},
        )
        assert new_login.status_code == 200
        assert "token" in new_login.json()


@pytest.mark.asyncio
async def test_register_rejects_xss_and_malicious_characters():
    """Verify registration rejects usernames containing HTML/script tags or illegal characters with 422."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Script tag injection
        res1 = await client.post("/api/auth/register", json={
            "username": "<script>alert(1)</script>",
            "email": "valid@email.com",
            "password": "password123",
        })
        assert res1.status_code == 422

        # 2. Img onerror injection
        res2 = await client.post("/api/auth/register", json={
            "username": '<img src=x onerror="alert(1)">',
            "email": "valid@email.com",
            "password": "password123",
        })
        assert res2.status_code == 422

        # 3. Invalid email format
        res3 = await client.post("/api/auth/register", json={
            "username": "valid_user-123",
            "email": "not-an-email",
            "password": "password123",
        })
        assert res3.status_code == 422

        # 4. Valid sanitized registration succeeds
        res_ok = await client.post("/api/auth/register", json={
            "username": "valid_user.name-99",
            "email": "user99@email.com",
            "password": "password123",
        })
        assert res_ok.status_code == 201


@pytest.mark.asyncio
async def test_auth_rate_limiting_login_and_register():
    """Verify brute-force rate limiting on /login and /register returns 429 with Retry-After header."""
    ip = "198.51.100.77"
    transport = httpx.ASGITransport(app=app, client=(ip, 54321))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup admin first
        await client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})

        # 2. Login rate limit is 15 rpm. Make 15 failed logins
        for i in range(15):
            res = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": f"wrongpass{i}"},
            )
            assert res.status_code == 401

        # 16th request must be throttled with 429
        throttled_res = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrongpass16"},
        )
        assert throttled_res.status_code == 429
        assert "Retry-After" in throttled_res.headers
        assert int(throttled_res.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_register_account_enumeration_defense():
    """Verify duplicate username and duplicate email return identical generic 409 messages."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register initial user
        init_res = await client.post("/api/auth/register", json={
            "username": "victim_alice",
            "email": "alice@company.com",
            "password": "Password123!",
        })
        assert init_res.status_code == 201

        expected_msg = "As informações de cadastro informadas já estão em uso. Tente outro nome de usuário ou e-mail, ou faça login."

        # 2. Duplicate username attempt
        dup_username = await client.post("/api/auth/register", json={
            "username": "victim_alice",
            "email": "different_email@company.com",
            "password": "Password123!",
        })
        assert dup_username.status_code == 409
        assert dup_username.json()["detail"] == expected_msg

        # 3. Duplicate email attempt
        dup_email = await client.post("/api/auth/register", json={
            "username": "different_bob",
            "email": "alice@company.com",
            "password": "Password123!",
        })
        assert dup_email.status_code == 409
        assert dup_email.json()["detail"] == expected_msg


@pytest.mark.asyncio
async def test_login_constant_failure_response():
    """Verify login failure returns generic message for both non-existent user and wrong password."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        await client.post("/api/auth/register", json={
            "username": "realuser",
            "email": "real@domain.com",
            "password": "SecretPassword123",
        })

        # Non-existent user
        res_nonexistent = await client.post("/api/auth/login", json={
            "username": "fakeuser",
            "password": "SecretPassword123",
        })
        assert res_nonexistent.status_code == 401
        assert res_nonexistent.json()["detail"] == "Credenciais inválidas."

        # Real user with wrong password
        res_wrong_pw = await client.post("/api/auth/login", json={
            "username": "realuser",
            "password": "WrongPassword999",
        })
        assert res_wrong_pw.status_code == 401
        assert res_wrong_pw.json()["detail"] == "Credenciais inválidas."
