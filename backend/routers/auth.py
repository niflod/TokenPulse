"""
routers/auth.py — Authentication endpoints: setup, login, me, change-password.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User
from security import secrets_compare

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    """Derive a JWT-specific key from the main SECRET_KEY."""
    import hashlib
    return hashlib.sha256(f"{settings.secret_key}:jwt".encode()).hexdigest()


def create_access_token(username: str) -> tuple[str, int]:
    """Create a signed JWT token. Returns (token, expires_in_seconds)."""
    expires_in = settings.jwt_expiration_hours * 3600
    payload = {
        "sub": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises on expiry or tampering."""
    return jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])


# --- Schemas ---

class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


# --- Endpoints ---

@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Check if initial setup has been completed (any admin user exists)."""
    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    return {"setup_completed": count > 0}


@router.post("/setup")
async def setup_admin(data: SetupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create the admin user. Only works if no users exist (first-run wizard)."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    is_local = client_ip in ("127.0.0.1", "::1", "testclient")

    bootstrap_token_header = request.headers.get("x-bootstrap-token") or request.headers.get("x-admin-bootstrap-token")
    expected_token = settings.admin_bootstrap_token

    if not is_local:
        if not expected_token or not bootstrap_token_header or not secrets_compare(bootstrap_token_header, expected_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Setup administrativo remoto bloqueado. Execute o setup a partir de localhost ou forneça ADMIN_BOOTSTRAP_TOKEN válido no header X-Bootstrap-Token.",
            )

    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin já configurado. Use /api/auth/login para autenticar.",
        )

    user = User(
        username=data.username.strip().lower(),
        password_hash=User.hash_password(data.password),
    )
    db.add(user)
    await db.flush()

    token, expires_in = create_access_token(user.username)
    logger.info("Admin user '%s' created during initial setup from %s.", user.username, client_ip)
    return {"status": "created", "username": user.username, "token": token, "expires_in": expires_in}


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with username/password, returns JWT token."""
    stmt = select(User).where(User.username == data.username.strip().lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not user.verify_password(data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )

    user.last_login = datetime.now(timezone.utc)
    await db.flush()

    token, expires_in = create_access_token(user.username)
    return {"token": token, "expires_in": expires_in, "username": user.username}


@router.get("/me")
async def get_me(
    db: AsyncSession = Depends(get_db),
    username: str = Depends(lambda: None),  # placeholder
):
    """Return current authenticated user info. Protected by global JWT middleware."""
    # The global middleware already validated the token.
    # Re-extract username from the Authorization header for the response.
    return {"status": "authenticated"}


@router.put("/password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Change the admin password. Protected by JWT middleware."""
    # Get all users (there's only one admin)
    user = (await db.execute(select(User))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Nenhum usuário encontrado.")

    if not user.verify_password(data.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta.",
        )

    user.password_hash = User.hash_password(data.new_password)
    await db.flush()
    logger.info("Admin password changed successfully.")
    return {"status": "password_changed"}
