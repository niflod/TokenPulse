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
        # Path after the triple slash
        path_part = db_url.split("///")[-1]
        dir_path = os.path.dirname(path_part)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
            logger.debug("Ensured data directory exists: %s", dir_path)


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
    """Create all tables defined in ORM models."""
    # Import models here so Base.metadata is populated before create_all
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialised.")
