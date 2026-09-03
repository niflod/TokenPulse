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
from pydantic import Field, field_validator
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

    # Security: SECRET_KEY is strictly required and must have at least 32 chars.
    # In development, if not provided, auto-generates a secure ephemeral key and warns.
    secret_key: str = Field(
        default_factory=lambda: os.getenv("SECRET_KEY") or secrets.token_hex(32)
    )

    # Optional Administrative API key for sensitive mutating endpoints
    admin_api_key: Optional[str] = None

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/dashboard.db"

    # Optional pre-configured provider keys (alternatives to UI config)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

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

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or len(v.strip()) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long. "
                "Generate one using: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        return v.strip()

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
