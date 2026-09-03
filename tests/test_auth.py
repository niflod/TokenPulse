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
