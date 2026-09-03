"""
config.py — Application settings via pydantic-settings.
Reads from .env file; exposes a `settings` singleton.
"""

from __future__ import annotations

import base64
import os
import secrets
from functools import lru_cache
from typing import List, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server (Default bound to 127.0.0.1 for local security)
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    # Environment: development vs production
    environment: str = Field(default="development", description="Ambiente de execução (development | production)")

    # Security: SECRET_KEY is strictly required and must have at least 32 chars in production.
    # In development, if not provided, auto-generates a secure ephemeral key.
    secret_key: Optional[str] = Field(
        default=None,
        description="Chave mestra para criptografia de credenciais (32+ caracteres em produção)"
    )

    # Optional Administrative API key for sensitive mutating endpoints
    admin_api_key: Optional[str] = None
    admin_bootstrap_token: Optional[str] = None

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/dashboard.db"

    # Optional pre-configured provider keys (alternatives to UI config)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None

    # Cache
    cache_ttl: int = 30  # seconds

    # CORS — restricted to known local origins by default
    cors_origins: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    # TokenPulse Gateway Settings
    gateway_enabled: bool = True
    gateway_connect_timeout: float = 10.0
    gateway_read_timeout: float = 120.0
    max_request_body_size: int = 10 * 1024 * 1024  # 10 MB
    telemetry_enabled: bool = True
    log_retention_days: int = 90  # days
    gateway_rate_limit_rpm: int = 120  # requests per minute per IP
    jwt_expiration_hours: int = 24  # JWT token TTL
    alert_webhook_url: Optional[str] = None  # Webhook (Discord/Slack/Generic) for triggered alerts
    provider_monthly_budget: Optional[float] = None  # Hard monthly budget limit in USD per provider
    gateway_cache_enabled: bool = True
    gateway_cache_default_ttl: int = 3600  # Default 1 hour in seconds

    # Security Hardening Controls
    ollama_allow_lan: bool = False
    allow_custom_provider_urls: bool = False
    gateway_allow_byok: bool = True
    gateway_require_auth: bool = True

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        env = (self.environment or "development").strip().lower()
        key = (self.secret_key or "").strip()
        if env != "development":
            if not key or len(key) < 32:
                raise ValueError(
                    "SECRET_KEY é obrigatória em ambiente de produção (ENVIRONMENT!=development) e deve possuir no mínimo 32 caracteres. "
                    "Gere uma chave com: python -c 'import secrets; print(secrets.token_hex(32))'"
                )
        else:
            if not key:
                # Ephemeral key for local development only
                self.secret_key = secrets.token_hex(32)
            elif len(key) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long. "
                    "Generate one using: python -c 'import secrets; print(secrets.token_hex(32))'"
                )
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Accept either a list or a comma-separated string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    def get_fernet_key(self) -> bytes:
        """
        Cryptographically derives a 32-byte Fernet key from secret_key using HKDF with SHA-256.
        Ensures uniform randomness and security regardless of source key formatting.
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"tokenpulse-fernet-salt-v1",
            info=b"tokenpulse-api-key-encryption",
        )
        derived = hkdf.derive(self.secret_key.encode("utf-8"))
        return base64.urlsafe_b64encode(derived)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Module-level singleton
settings: Settings = get_settings()
