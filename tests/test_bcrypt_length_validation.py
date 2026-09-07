"""
tests/test_bcrypt_length_validation.py — Tests verifying strict password length boundary (8-72 chars)
to prevent silent bcrypt truncation.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import pytest
import pytest_asyncio
from database import AsyncSessionLocal, init_db
from main import app
from models import User
from sqlalchemy import delete


@pytest_asyncio.fixture(autouse=True)
async def clean_users_db():
    await init_db()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()


@pytest.mark.asyncio
async def test_register_password_72_byte_limit():
    """Verify password of 73 chars is rejected (422) and 72 chars is accepted (201)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Password with 73 chars -> Rejected with 422 Unprocessable Entity
        pw_73 = "A" * 73
        res_73 = await client.post("/api/auth/register", json={
            "username": "user_73_chars",
            "email": "user73@domain.com",
            "password": pw_73,
        })
        assert res_73.status_code == 422

        # 2. Password with 72 chars -> Accepted with 201 Created
        pw_72 = "A" * 72
        res_72 = await client.post("/api/auth/register", json={
            "username": "user_72_chars",
            "email": "user72@domain.com",
            "password": pw_72,
        })
        assert res_72.status_code == 201
        assert res_72.json()["username"] == "user_72_chars"

        # 3. Login with 72-char password works
        res_login = await client.post("/api/auth/login", json={
            "username": "user_72_chars",
            "password": pw_72,
        })
        assert res_login.status_code == 200
        token = res_login.json()["token"]

        # 4. Change password with 73-char new password -> Rejected with 422
        res_change_bad = await client.put(
            "/api/auth/password",
            json={"current_password": pw_72, "new_password": "B" * 73},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_change_bad.status_code == 422

        # 5. Change password with 72-char new password -> Accepted with 200
        res_change_ok = await client.put(
            "/api/auth/password",
            json={"current_password": pw_72, "new_password": "B" * 72},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_change_ok.status_code == 200
