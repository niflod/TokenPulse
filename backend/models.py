"""
models.py — SQLAlchemy ORM models for the AI Usage Dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderConfig(Base):
    """Stores per-provider configuration including encrypted API keys."""

    __tablename__ = "provider_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # The API key is stored encrypted; never store plaintext
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    @staticmethod
    def encrypt_key(raw_key: str, secret: bytes) -> str:
        """Encrypt a plaintext API key using Fernet symmetric encryption."""
        f = Fernet(secret)
        return f.encrypt(raw_key.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decrypt_key_static(encrypted_key: str, secret: bytes) -> str | None:
        """Decrypt an encrypted API key directly using Fernet key."""
        if not encrypted_key:
            return None
        f = Fernet(secret)
        return f.decrypt(encrypted_key.encode("utf-8")).decode("utf-8")

    def decrypt_key(self, secret: bytes) -> str | None:
        """Decrypt and return the stored API key, or None if not set."""
        if not self.api_key_encrypted:
            return None
        try:
            return self.decrypt_key_static(self.api_key_encrypted, secret)
        except Exception:
            logger.error("Failed to decrypt API key for provider '%s'", self.name)
            return None

    def masked_key(self) -> str | None:
        """Return a masked representation of the key (e.g. sk-...****)."""
        if not self.api_key_encrypted:
            return None
        # We only show a placeholder — we never decrypt just to mask
        return "****"


class RequestLog(Base):
    """Records individual API requests routed through the dashboard proxy."""

    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_input: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_output: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    # TokenPulse internal unique correlation ID
    request_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    # Upstream provider's native request ID
    provider_request_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Advanced telemetry & Streaming metrics
    time_to_first_token_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    stream_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Failover & Fallback metadata
    fallback_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    original_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Response Caching metadata
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AlertConfig(Base):
    """Configures thresholds for anomaly / usage alerts."""

    __tablename__ = "alert_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 'all' means the alert applies to every provider
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="all")
    # e.g. 'daily_usage_pct', 'error_rate', 'latency_ms'
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class User(Base):
    """Admin user for dashboard authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_login: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @staticmethod
    def hash_password(password: str) -> str:
        import bcrypt
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        import bcrypt
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))


class ClientApiKey(Base):
    """Virtual API key issued by TokenPulse for client applications."""

    __tablename__ = "client_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    rate_limit_rpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FallbackRule(Base):
    """Model failover routing rule when primary provider/model fails."""

    __tablename__ = "fallback_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class GatewayResponseCache(Base):
    """
    Cached responses for identical Gateway requests.
    Indexed by deterministic SHA-256 hash of canonical request parameters.
    """

    __tablename__ = "gateway_response_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_saved_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

