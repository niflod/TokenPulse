"""
database.py — Async SQLAlchemy engine, session factory, and DB init.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def _ensure_data_dir() -> None:
    """Create the data/ directory if it doesn't exist (needed for SQLite)."""
    db_url = settings.database_url
    # Extract file path from SQLite URL, e.g. sqlite+aiosqlite:///./data/dashboard.db
    if "sqlite" in db_url:
        path_part = db_url.split("///")[-1]
        dir_path = os.path.dirname(path_part)
        if dir_path:
            os.makedirs(dir_path, mode=0o700, exist_ok=True)
            try:
                os.chmod(dir_path, 0o700)
                if os.path.exists(path_part):
                    os.chmod(path_part, 0o600)
            except OSError:
                pass
            logger.debug("Ensured data directory exists with secure permissions: %s", dir_path)


_ensure_data_dir()

# Create async engine; echo only in debug mode
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite-specific: allow usage across async tasks
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# Configure SQLite pragmas for high concurrency and async safety
from sqlalchemy import event


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in settings.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Session factory — expire_on_commit=False keeps objects usable after commit
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables defined in ORM models and migrate columns if needed."""
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _migrate_sqlite_columns(sync_conn):
            from sqlalchemy import text
            res = sync_conn.execute(text("PRAGMA table_info(request_logs)"))
            existing_cols = {row[1] for row in res.fetchall()}
            new_cols = [
                ("provider_request_id", "VARCHAR(256)"),
                ("time_to_first_token_ms", "FLOAT"),
                ("stream_duration_ms", "FLOAT"),
                ("cached_input_tokens", "INTEGER"),
                ("reasoning_tokens", "INTEGER"),
                ("finish_reason", "VARCHAR(64)"),
                ("fallback_triggered", "BOOLEAN DEFAULT 0"),
                ("original_provider", "VARCHAR(64)"),
                ("original_model", "VARCHAR(128)"),
                ("fallback_reason", "VARCHAR(64)"),
                ("cache_hit", "BOOLEAN DEFAULT 0"),
                ("usage_source", "VARCHAR(32)"),
                ("user_id", "INTEGER"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in existing_cols:
                    sync_conn.execute(text(f"ALTER TABLE request_logs ADD COLUMN {col_name} {col_type}"))
                    logger.info("Migrated SQLite: added column %s to request_logs", col_name)

            # Migrate provider_configs
            res_prov = sync_conn.execute(text("PRAGMA table_info(provider_configs)"))
            prov_cols = {row[1] for row in res_prov.fetchall()}
            for c_name, c_type in [
                ("user_id", "INTEGER"),
                ("last_synced_at", "TIMESTAMP"),
                ("sync_status", "VARCHAR(32) DEFAULT 'idle'"),
                ("sync_error", "TEXT"),
            ]:
                if c_name not in prov_cols:
                    sync_conn.execute(text(f"ALTER TABLE provider_configs ADD COLUMN {c_name} {c_type}"))
                    logger.info("Migrated SQLite: added column %s to provider_configs", c_name)

            # Drop legacy unique index on name to allow per-user provider configurations
            try:
                sync_conn.execute(text("DROP INDEX IF EXISTS ix_provider_configs_name"))
                sync_conn.execute(text("CREATE INDEX IF NOT EXISTS ix_provider_configs_name ON provider_configs (name)"))
            except Exception as ex:
                logger.warning("Could not recreate index on provider_configs: %s", ex)

            # Migrate alert_configs
            res_alerts = sync_conn.execute(text("PRAGMA table_info(alert_configs)"))
            alert_cols = {row[1] for row in res_alerts.fetchall()}
            for c_name, c_type in [("webhook_url", "VARCHAR(512)"), ("user_id", "INTEGER")]:
                if c_name not in alert_cols:
                    sync_conn.execute(text(f"ALTER TABLE alert_configs ADD COLUMN {c_name} {c_type}"))
                    logger.info("Migrated SQLite: added column %s to alert_configs", c_name)

            # Migrate users
            res_users = sync_conn.execute(text("PRAGMA table_info(users)"))
            user_cols = {row[1] for row in res_users.fetchall()}
            if "email" not in user_cols:
                sync_conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(256)"))
                logger.info("Migrated SQLite: added column email to users")

            # Migrate client_api_keys
            res_keys = sync_conn.execute(text("PRAGMA table_info(client_api_keys)"))
            key_cols = {row[1] for row in res_keys.fetchall()}
            if "user_id" not in key_cols:
                sync_conn.execute(text("ALTER TABLE client_api_keys ADD COLUMN user_id INTEGER"))
                logger.info("Migrated SQLite: added column user_id to client_api_keys")

            # Migrate fallback_rules
            res_fb = sync_conn.execute(text("PRAGMA table_info(fallback_rules)"))
            fb_cols = {row[1] for row in res_fb.fetchall()}
            if "user_id" not in fb_cols:
                sync_conn.execute(text("ALTER TABLE fallback_rules ADD COLUMN user_id INTEGER"))
                logger.info("Migrated SQLite: added column user_id to fallback_rules")

            # Migrate gateway_response_cache
            res_cache = sync_conn.execute(text("PRAGMA table_info(gateway_response_cache)"))
            cache_cols = {row[1] for row in res_cache.fetchall()}
            if "user_id" not in cache_cols:
                sync_conn.execute(text("ALTER TABLE gateway_response_cache ADD COLUMN user_id INTEGER"))
                logger.info("Migrated SQLite: added column user_id to gateway_response_cache")

        if "sqlite" in settings.database_url:
            await conn.run_sync(_migrate_sqlite_columns)

    # Seed default fallback rules if empty
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from models import FallbackRule
        res = await session.execute(select(FallbackRule).limit(1))
        if not res.scalar_one_or_none():
            default_rules = [
                FallbackRule(source_provider="openai", source_model="gpt-4o", target_provider="groq", target_model="llama-3.3-70b-versatile", priority=1),
                FallbackRule(source_provider="openai", source_model="gpt-4o", target_provider="mistral", target_model="mistral-large-latest", priority=2),
                FallbackRule(source_provider="openai", source_model="gpt-4o-mini", target_provider="groq", target_model="llama-3.1-8b-instant", priority=1),
                FallbackRule(source_provider="openai", source_model="gpt-4o-mini", target_provider="mistral", target_model="mistral-small-latest", priority=2),
                FallbackRule(source_provider="anthropic", source_model="claude-3-5-sonnet-20241022", target_provider="groq", target_model="llama-3.3-70b-versatile", priority=1),
            ]
            session.add_all(default_rules)
            await session.commit()
            logger.info("Seeded %d default fallback rules.", len(default_rules))

    logger.info("Database tables initialised.")
