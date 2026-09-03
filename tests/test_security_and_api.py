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
