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
        assert "TokenPulse — Monitore custos e uso de APIs de IA" in content
        assert "og:image" in content
        assert "twitter:card" in content
        assert 'rel="canonical"' in content
        assert 'id="faq"' in content
        assert "schema.org" in content
        assert "FAQPage" in content
        assert "Organization" in content


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


@pytest.mark.asyncio
async def test_seo_crawler_assets():
    """Valida a entrega correta de robots.txt, sitemap.xml e favicon.svg."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_robots = await client.get("/robots.txt")
        assert res_robots.status_code == 200
        assert "User-agent: *" in res_robots.text
        assert "Disallow: /dashboard" in res_robots.text
        assert "Sitemap: https://tokenpulse.netlify.app/sitemap.xml" in res_robots.text

        res_sitemap = await client.get("/sitemap.xml")
        assert res_sitemap.status_code == 200
        assert "https://tokenpulse.netlify.app/" in res_sitemap.text

        res_fav = await client.get("/favicon.svg")
        assert res_fav.status_code == 200
        assert "<svg" in res_fav.text


@pytest.mark.asyncio
async def test_nonexistent_route_returns_404():
    """Garante que rotas inexistentes retornem status HTTP 404 e a página 404 estilizada."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/rota-inexistente-xyz", headers={"Accept": "text/html"})
        assert res.status_code == 404
        assert "404" in res.text
        assert "Página Não Encontrada" in res.text


@pytest.mark.asyncio
async def test_public_demo_endpoint_accessible_without_auth():
    """Garante que /api/metrics/demo seja publicamente acessível para o tour de demonstração."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/metrics/demo")
        assert res.status_code == 200
        data = res.json()
        assert data.get("demo") is True
        assert "summary" in data
        assert "timeseries" in data


@pytest.mark.asyncio
async def test_production_docs_suppression(monkeypatch):
    """Verifica se /docs e /openapi.json são desativados quando o ambiente é production."""
    import importlib
    import main as main_module
    from config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "012345678901234567890123456789012345")

    # Recarrega módulo principal para aplicar docs_url=None em production
    prod_app = importlib.reload(main_module).app
    transport = httpx.ASGITransport(app=prod_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_docs = await client.get("/docs")
        assert res_docs.status_code == 404

        res_openapi = await client.get("/openapi.json")
        assert res_openapi.status_code == 404

    # Restaura módulo com ambiente padrão
    monkeypatch.setattr(settings, "environment", "development")
    importlib.reload(main_module)


def test_netlify_toml_security_headers():
    """Valida presença dos cabeçalhos CSP e HSTS no arquivo netlify.toml."""
    toml_path = Path(__file__).resolve().parent.parent / "netlify.toml"
    assert toml_path.exists()
    content = toml_path.read_text(encoding="utf-8")

    assert "Strict-Transport-Security" in content
    assert "max-age=31536000; includeSubDomains" in content
    assert "Content-Security-Policy" in content
    assert "default-src 'self'" in content
    assert "https://cdn.jsdelivr.net" in content


@pytest.mark.asyncio
async def test_jwt_middleware_rejects_anonymous_admin_key_on_protected_endpoints():
    """Garante que X-Admin-Key isolado sem token de usuário seja rejeitado no middleware comum."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/logs", headers={"X-Admin-Key": "any-key-value"})
        assert res.status_code == 401
        assert "Autenticação necessária" in res.json()["detail"]
