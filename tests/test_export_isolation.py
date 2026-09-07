"""
tests/test_export_isolation.py — Multi-tenant data export isolation test suite.
Verifies that /api/export/csv and /api/export/json strictly isolate logs by tenant user_id.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import pytest
import pytest_asyncio
from database import AsyncSessionLocal, init_db
from main import app
from models import RequestLog, User
from sqlalchemy import delete


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    await init_db()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RequestLog))
        await db.execute(delete(User))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RequestLog))
        await db.execute(delete(User))
        await db.commit()


@pytest.mark.asyncio
async def test_export_endpoints_require_authentication():
    """Verify that export endpoints reject unauthenticated requests with HTTP 401."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_csv = await client.get("/api/export/csv")
        assert res_csv.status_code == 401

        res_json = await client.get("/api/export/json")
        assert res_json.status_code == 401


@pytest.mark.asyncio
async def test_multi_tenant_export_isolation():
    """Verify Tenant Alice cannot see Tenant Bob's request logs in CSV or JSON exports."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Alice
        res_alice = await client.post("/api/auth/register", json={
            "username": "export_alice",
            "email": "alice@export.com",
            "password": "Password123!",
        })
        assert res_alice.status_code == 201
        alice_data = res_alice.json()
        alice_token = alice_data["token"]
        alice_id = alice_data["user_id"]
        alice_headers = {"Authorization": f"Bearer {alice_token}"}

        # 2. Register Bob
        res_bob = await client.post("/api/auth/register", json={
            "username": "export_bob",
            "email": "bob@export.com",
            "password": "Password123!",
        })
        assert res_bob.status_code == 201
        bob_data = res_bob.json()
        bob_token = bob_data["token"]
        bob_id = bob_data["user_id"]
        bob_headers = {"Authorization": f"Bearer {bob_token}"}

        # 3. Seed RequestLogs for Alice and Bob
        async with AsyncSessionLocal() as db:
            log_alice_1 = RequestLog(
                user_id=alice_id,
                provider="openai",
                model="gpt-4o-alice-exclusive",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                cost_total=0.005,
                timestamp=datetime.now(timezone.utc),
                request_id="req-alice-secret-001",
            )
            log_alice_2 = RequestLog(
                user_id=alice_id,
                provider="anthropic",
                model="claude-3-5-alice",
                input_tokens=200,
                output_tokens=80,
                total_tokens=280,
                cost_total=0.010,
                timestamp=datetime.now(timezone.utc),
                request_id="req-alice-secret-002",
            )
            log_bob_1 = RequestLog(
                user_id=bob_id,
                provider="groq",
                model="llama-3-bob-confidential",
                input_tokens=300,
                output_tokens=120,
                total_tokens=420,
                cost_total=0.002,
                timestamp=datetime.now(timezone.utc),
                request_id="req-bob-secret-999",
            )
            db.add_all([log_alice_1, log_alice_2, log_bob_1])
            await db.commit()

        # 4. Alice exports CSV -> Must contain only Alice's logs
        alice_csv_res = await client.get("/api/export/csv", headers=alice_headers)
        assert alice_csv_res.status_code == 200
        alice_csv_text = alice_csv_res.text
        assert "gpt-4o-alice-exclusive" in alice_csv_text
        assert "req-alice-secret-001" in alice_csv_text
        assert "claude-3-5-alice" in alice_csv_text
        assert "llama-3-bob-confidential" not in alice_csv_text
        assert "req-bob-secret-999" not in alice_csv_text

        # 5. Alice exports JSON -> Must contain only Alice's logs
        alice_json_res = await client.get("/api/export/json", headers=alice_headers)
        assert alice_json_res.status_code == 200
        alice_items = alice_json_res.json()
        assert len(alice_items) == 2
        alice_req_ids = {item["request_id"] for item in alice_items}
        assert alice_req_ids == {"req-alice-secret-001", "req-alice-secret-002"}

        # 6. Bob exports CSV -> Must contain only Bob's logs
        bob_csv_res = await client.get("/api/export/csv", headers=bob_headers)
        assert bob_csv_res.status_code == 200
        bob_csv_text = bob_csv_res.text
        assert "llama-3-bob-confidential" in bob_csv_text
        assert "req-bob-secret-999" in bob_csv_text
        assert "gpt-4o-alice-exclusive" not in bob_csv_text
        assert "req-alice-secret-001" not in bob_csv_text

        # 7. Bob exports JSON -> Must contain only Bob's logs
        bob_json_res = await client.get("/api/export/json", headers=bob_headers)
        assert bob_json_res.status_code == 200
        bob_items = bob_json_res.json()
        assert len(bob_items) == 1
        assert bob_items[0]["request_id"] == "req-bob-secret-999"
        assert bob_items[0]["model"] == "llama-3-bob-confidential"
