"""
tests/test_web_routes.py — Verificação de rotas web e páginas da plataforma Web SaaS.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import pytest
from main import app


@pytest.mark.asyncio
async def test_root_serves_landing_page():
    """Garante que a raiz (/) sirva a Landing Page pública."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        content = res.text
        assert "TOKENPULSE" in content
        assert "Observe seu consumo de IA" in content
        assert "Ver Demonstração ao Vivo" in content
        assert "/signup.html" in content


@pytest.mark.asyncio
async def test_dashboard_routes():
    """Garante que /dashboard e /app sirvam o painel autenticado."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_dash = await client.get("/dashboard")
        assert res_dash.status_code == 200
        assert "TokenPulse — Dashboard" in res_dash.text
        assert "app-layout" in res_dash.text

        res_app = await client.get("/app")
        assert res_app.status_code == 200
        assert "TokenPulse — Dashboard" in res_app.text


@pytest.mark.asyncio
async def test_auth_pages_and_api_ping():
    """Garante que telas de login, signup e o endpoint de health permaneçam íntegros."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_login = await client.get("/login.html")
        assert res_login.status_code == 200
        assert "Entrar" in res_login.text

        res_signup = await client.get("/signup.html")
        assert res_signup.status_code == 200
        assert "Criar Nova Conta" in res_signup.text

        res_ping = await client.get("/api/ping")
        assert res_ping.status_code == 200
        assert res_ping.json()["status"] == "ok"
