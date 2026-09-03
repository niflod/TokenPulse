"""
tests/test_security_and_api.py — Comprehensive tests for TokenPulse security, pricing, and APIs.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import pytest
from fastapi import HTTPException
from config import Settings
from models import ProviderConfig
from pricing import lookup_pricing
from security import validate_provider_base_url


def test_secret_key_validation():
    """Ensure weak secret keys are rejected."""
    with pytest.raises(ValueError, match="SECRET_KEY must be at least 32 characters long"):
        Settings(secret_key="too-short")

    valid_key = "a" * 32
    s = Settings(secret_key=valid_key)
    assert len(s.secret_key) >= 32

    # In production, missing or empty SECRET_KEY must raise ValueError
    with pytest.raises(ValueError, match="SECRET_KEY é obrigatória em ambiente de produção"):
        Settings(environment="production", secret_key="")

    with pytest.raises(ValueError, match="SECRET_KEY é obrigatória em ambiente de produção"):
        Settings(environment="production", secret_key=None)

    # In development, missing SECRET_KEY auto-generates a 64-char hex key
    dev_s = Settings(environment="development", secret_key=None)
    assert len(dev_s.secret_key) == 64


def test_fernet_hkdf_derivation():
    """Test that HKDF derivation produces reproducible and valid Fernet keys."""
    valid_key = "random_test_secret_key_longer_than_32_chars_12345"
    s = Settings(secret_key=valid_key)
    fkey = s.get_fernet_key()

    # Fernet key must be 44 URL-safe base64 bytes (representing 32 raw bytes)
    assert len(fkey) == 44

    # Test round-trip encryption/decryption
    raw_api_key = "sk-test-super-secret-provider-key-999"
    encrypted = ProviderConfig.encrypt_key(raw_api_key, fkey)
    assert encrypted != raw_api_key

    decrypted = ProviderConfig.decrypt_key_static(encrypted, fkey)
    assert decrypted == raw_api_key


def test_ssrf_protection():
    """Verify that localhost, loopback and private IPs are blocked."""
    # Localhost should be blocked
    with pytest.raises(HTTPException) as exc1:
        validate_provider_base_url("openai", "https://localhost/v1")
    assert exc1.value.status_code == 400

    # 127.0.0.1 should be blocked
    with pytest.raises(HTTPException) as exc2:
        validate_provider_base_url("openai", "https://127.0.0.1/v1")
    assert exc2.value.status_code == 400

    # Non-HTTPS should be blocked
    with pytest.raises(HTTPException) as exc3:
        validate_provider_base_url("openai", "http://api.openai.com/v1")
    assert exc3.value.status_code == 400

    # Valid HTTPS URL should pass
    valid_url = "https://api.openai.com/v1"
    cleaned = validate_provider_base_url("openai", valid_url)
    assert cleaned == "https://api.openai.com/v1"

    # Custom domain without ALLOW_CUSTOM_PROVIDER_URLS must be blocked
    with pytest.raises(HTTPException) as exc4:
        validate_provider_base_url("openai", "https://unauthorized-domain.com/v1")
    assert exc4.value.status_code == 400
    assert "não é permitido para o provedor" in exc4.value.detail

    # Ollama localhost is allowed
    ollama_local = validate_provider_base_url("ollama", "http://127.0.0.1:11434")
    assert ollama_local == "http://127.0.0.1:11434"

    # Ollama external/LAN is blocked by default without OLLAMA_ALLOW_LAN
    with pytest.raises(HTTPException) as exc5:
        validate_provider_base_url("ollama", "http://192.168.1.50:11434")
    assert exc5.value.status_code == 400
    assert "Ollama é restrito a instâncias locais" in exc5.value.detail


def test_ssrf_dns_rebinding_blocked(monkeypatch):
    """Verify that domains resolving to local/private IPs are blocked (DNS Rebinding defense)."""
    import socket
    from config import settings

    monkeypatch.setattr(settings, "allow_custom_provider_urls", True)

    def fake_getaddrinfo(host, port, proto=0):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(HTTPException) as exc:
        validate_provider_base_url("openai", "https://attacker-rebind.internal/v1")
    assert exc.value.status_code == 400
    assert "resolve para endereço IP restrito" in exc.value.detail


def test_centralized_pricing():
    """Verify that centralized pricing correctly identifies common models."""
    inp, out, ctx, max_tok = lookup_pricing("openai", "gpt-4o")
    assert inp == 2.50
    assert out == 10.00
    assert ctx == 128000

    inp_c, out_c, ctx_c, _ = lookup_pricing("anthropic", "claude-3-5-sonnet-20241022")
    assert inp_c == 3.00
    assert out_c == 15.00
    assert ctx_c == 200000

    inp_g, out_g, _, _ = lookup_pricing("gemini", "gemini-2.0-flash")
    assert inp_g == 0.10
    assert out_g == 0.40


@pytest.mark.asyncio
async def test_demo_endpoint_isolation():
    """Ensure demo endpoint produces expected TokenPulse data structure."""
    from services.demo import generate_demo_data

    demo = generate_demo_data()
    assert demo["demo"] is True
    assert "summary" in demo
    assert "byModel" in demo
    assert "timeseries" in demo
    assert len(demo["timeseries"]) == 24


def test_log_redaction_comprehensive():
    """Verify that redact_sensitive_text masks tokens, passwords, cookies, and query params."""
    from security import redact_sensitive_text

    raw_err = "Error with cookie: session_id=secret12345; auth=token_abcdef123456 and sk-proj-123456789012345678"
    redacted = redact_sensitive_text(raw_err)
    assert "secret12345" not in redacted
    assert "token_abcdef123456" not in redacted
    assert "sk-proj-123456789012345678" not in redacted
    assert "[REDACTED]" in redacted

    raw_qs = "GET /test?token=my_secret_jwt_token_123&other=val"
    redacted_qs = redact_sensitive_text(raw_qs)
    assert "my_secret_jwt_token_123" not in redacted_qs


@pytest.mark.asyncio
async def test_security_headers_and_csp():
    """Verify that responses include Permissions-Policy, nosniff, and CSP without unsafe-inline in script-src."""
    import httpx
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ping")
        assert res.status_code == 200
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "DENY"
        assert "Permissions-Policy" in res.headers
        csp = res.headers.get("Content-Security-Policy", "")
        assert "script-src 'self'" in csp
        assert "script-src 'self' 'unsafe-inline'" not in csp

