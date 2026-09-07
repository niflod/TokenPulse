"""
test_database_postgres_support.py — Tests for PostgreSQL support and DATABASE_URL normalization.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from config import Settings


def test_database_url_normalization_postgres_prefix():
    """Verify postgres:// is rewritten to postgresql+asyncpg://."""
    s = Settings(
        database_url="postgres://user:secret@ep-cool-db.us-east-2.aws.neon.tech/tokenpulse?sslmode=require",
        jwt_secret_key="a" * 32,
        encryption_master_key="b" * 32,
    )
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert "user:secret@ep-cool-db.us-east-2.aws.neon.tech/tokenpulse" in s.database_url


def test_database_url_normalization_postgresql_prefix():
    """Verify postgresql:// is rewritten to postgresql+asyncpg://."""
    s = Settings(
        database_url="postgresql://postgres:secret@db.supabase.co:5432/postgres",
        jwt_secret_key="a" * 32,
        encryption_master_key="b" * 32,
    )
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert "postgres:secret@db.supabase.co:5432/postgres" in s.database_url


def test_database_url_normalization_already_asyncpg():
    """Verify postgresql+asyncpg:// remains untouched."""
    url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
    s = Settings(
        database_url=url,
        jwt_secret_key="a" * 32,
        encryption_master_key="b" * 32,
    )
    assert s.database_url == url


def test_database_url_normalization_sqlite_unchanged():
    """Verify SQLite database URL remains untouched."""
    url = "sqlite+aiosqlite:///./data/dashboard.db"
    s = Settings(
        database_url=url,
        jwt_secret_key="a" * 32,
        encryption_master_key="b" * 32,
    )
    assert s.database_url == url


def test_asyncpg_engine_initialization():
    """Verify that SQLAlchemy can instantiate an asyncpg engine with resilient pool options."""
    pg_url = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    engine = create_async_engine(
        pg_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    assert engine.name == "postgresql"
    assert engine.dialect.driver == "asyncpg"
