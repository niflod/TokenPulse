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
from security import check_auth_rate_limit, secrets_compare

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_ALGORITHM = "HS256"


def _get_jwt_secret() -> str:
    """Derive a JWT-specific key from the main SECRET_KEY."""
    import hashlib
    return hashlib.sha256(f"{settings.secret_key}:jwt".encode()).hexdigest()


def create_access_token(username: str, user_id: Optional[int] = None) -> tuple[str, int]:
    """Create a signed JWT token. Returns (token, expires_in_seconds)."""
    expires_in = settings.jwt_expiration_hours * 3600
    payload = {
        "sub": username,
        "user_id": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises on expiry or tampering."""
    return jwt.decode(token, _get_jwt_secret(), algorithms=[JWT_ALGORITHM])


# --- Schemas ---

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(..., min_length=5, max_length=256, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=72)


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=72)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=72)


# --- Endpoints ---

@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Check if initial setup has been completed (any admin user exists)."""
    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    return {"setup_completed": count > 0}


@router.post("/setup")
async def setup_admin(data: SetupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create the admin user. Only works if no users exist (first-run wizard)."""
    check_auth_rate_limit(request, action="setup", custom_rpm=min(10, settings.auth_rate_limit_rpm))
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

    token, expires_in = create_access_token(user.username, user.id)
    logger.info("Admin user '%s' created during initial setup from %s.", user.username, client_ip)
    return {"status": "created", "username": user.username, "token": token, "expires_in": expires_in}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Public registration for multi-tenant SaaS accounts."""
    check_auth_rate_limit(request, action="register", custom_rpm=min(10, settings.auth_rate_limit_rpm))
    clean_username = data.username.strip().lower()
    clean_email = data.email.strip().lower()

    # Check if username or email exists
    stmt_user = select(User).where(User.username == clean_username)
    user_exists = (await db.execute(stmt_user)).scalar_one_or_none() is not None

    stmt_email = select(User).where(User.email == clean_email)
    email_exists = (await db.execute(stmt_email)).scalar_one_or_none() is not None

    if user_exists or email_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="As informações de cadastro informadas já estão em uso. Tente outro nome de usuário ou e-mail, ou faça login.",
        )

    user = User(
        username=clean_username,
        email=clean_email,
        password_hash=User.hash_password(data.password),
    )
    db.add(user)
    await db.flush()

    token, expires_in = create_access_token(user.username, user.id)
    logger.info("New SaaS user '%s' (%s) registered successfully.", user.username, user.email)
    return {
        "status": "created",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "token": token,
        "expires_in": expires_in,
    }


@router.post("/login")
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate with username/password or email/password, returns JWT token."""
    check_auth_rate_limit(request, action="login", custom_rpm=min(15, settings.auth_rate_limit_rpm))
    from sqlalchemy import or_
    clean_ident = data.username.strip().lower()
    stmt = select(User).where(or_(User.username == clean_ident, User.email == clean_ident))
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not user.verify_password(data.password):
        if not user:
            import bcrypt
            bcrypt.checkpw(data.password.encode("utf-8"), b"$2b$12$e8Y04Z.wKk7pB/6a9u2/ueXw2hQk3E9V2K0EaYf7K9j9X7q6R0Qey")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
        )

    user.last_login = datetime.now(timezone.utc)
    await db.flush()

    token, expires_in = create_access_token(user.username, user.id)
    return {
        "token": token,
        "expires_in": expires_in,
        "username": user.username,
        "email": user.email,
        "user_id": user.id,
    }


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that resolves the authenticated User from JWT Bearer token."""
    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if not token:
        admin_key = request.headers.get("x-admin-key", "")
        if admin_key and settings.admin_api_key:
            import hmac
            if hmac.compare_digest(admin_key.encode(), settings.admin_api_key.encode()):
                stmt = select(User).where(User.username == "admin")
                admin_user = (await db.execute(stmt)).scalar_one_or_none()
                if admin_user:
                    return admin_user
                return User(id=1, username="admin", email="admin@local")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("user_id")
    username = payload.get("sub")

    user = None
    if user_id:
        user = await db.get(User, user_id)
    elif username:
        stmt = select(User).where(User.username == username)
        user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        if username == "admin":
            user = User(id=1, username="admin", email="admin@local")
        elif user_id or username:
            user = User(id=user_id or 1, username=username or f"user_{user_id}", email=f"{username or user_id}@local")
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não encontrado.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return user


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {
        "status": "authenticated",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
    }


@router.put("/password")
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the password for the current authenticated user."""
    db_user = await db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if not db_user.verify_password(data.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta.",
        )

    db_user.password_hash = User.hash_password(data.new_password)
    await db.flush()
    logger.info("User '%s' password changed successfully.", user.username)
    return {"status": "password_changed"}
