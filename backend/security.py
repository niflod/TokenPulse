"""
security.py — Administrative authentication and SSRF protection for TokenPulse.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from config import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

# Official allowed domains for known providers
OFFICIAL_PROVIDER_DOMAINS = {
    "openai": ["api.openai.com"],
    "anthropic": ["api.anthropic.com"],
    "gemini": ["generativelanguage.googleapis.com"],
    "groq": ["api.groq.com"],
    "mistral": ["api.mistral.ai"],
    "ollama": ["localhost", "127.0.0.1"],
}

# Private and reserved IP blocks for SSRF prevention
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

async def require_admin(
    request: Request,
    x_admin_key: Optional[str] = Security(api_key_header),
    authorization: Optional[str] = Header(None),
) -> bool:
    """
    Validates administrative access for mutating endpoints.
    Accepts X-Admin-Key header, JWT Bearer token (header or query param), or open access if no admin key configured.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif request.query_params.get("token"):
        token = request.query_params.get("token")

    if token:
        try:
            from routers.auth import decode_access_token
            decode_access_token(token)
            return True
        except Exception:
            pass  # Fall through to X-Admin-Key check

    configured_key = settings.admin_api_key
    if not configured_key:
        return True  # Open by default if no admin key was specified in settings

    # Check X-Admin-Key header
    if x_admin_key and secrets_compare(x_admin_key, configured_key):
        return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Acesso administrativo não autorizado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_jwt(
    authorization: Optional[str] = Header(None),
) -> str:
    """
    FastAPI dependency that validates a JWT Bearer token.
    Returns the username (sub claim) if valid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    try:
        from routers.auth import decode_access_token
        payload = decode_access_token(token)
        return payload["sub"]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def secrets_compare(val1: str, val2: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


def _resolve_and_check_ips(hostname: str, allow_private: bool = False) -> None:
    """
    Resolves hostname to IP addresses and verifies none belong to blocked ranges.
    Prevents DNS rebinding attacks where domain points to loopback or private ranges.
    """
    import socket

    try:
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        blocked_nets = (
            [
                ipaddress.ip_network("0.0.0.0/8"),
                ipaddress.ip_network("127.0.0.0/8"),
                ipaddress.ip_network("169.254.0.0/16"),
                ipaddress.ip_network("::1/128"),
                ipaddress.ip_network("fe80::/10"),
            ]
            if allow_private
            else BLOCKED_IP_NETWORKS
        )
        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            for net in blocked_nets:
                if ip in net:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"SSRF Protection: Hostname '{hostname}' resolve para endereço IP restrito ({ip_str}).",
                    )
    except socket.gaierror:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"URL de provedor inválida: falha na resolução de DNS para o hostname '{hostname}'.",
        )


def validate_provider_base_url(provider: str, base_url: Optional[str]) -> Optional[str]:
    """
    Validates provider base URL against SSRF attacks.
    Ensures HTTPS protocol (except Ollama local), resolves DNS to prevent DNS rebinding,
    and blocks access to internal networks, loopback, or unauthorized custom domains.
    """
    if not base_url or not base_url.strip():
        return None

    cleaned_url = base_url.strip().rstrip("/")
    parsed = urlparse(cleaned_url)

    provider_name = provider.lower().strip()

    # 1. Scheme check: only HTTPS allowed for cloud providers, HTTP/HTTPS for Ollama
    if provider_name == "ollama":
        if parsed.scheme.lower() not in ("http", "https"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ollama requer protocolo HTTP ou HTTPS.",
            )
    else:
        if parsed.scheme.lower() != "https":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Apenas conexões seguras HTTPS são permitidas para base_url.",
            )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL de provedor inválida: hostname ausente.",
        )

    # 2. Ollama specific handling
    if provider_name == "ollama":
        ollama_local = ("localhost", "127.0.0.1", "::1")
        if hostname in ollama_local:
            return cleaned_url
        if not getattr(settings, "ollama_allow_lan", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"SSRF Protection: Ollama é restrito a instâncias locais (localhost, 127.0.0.1). "
                    "Para permitir instâncias em rede local (LAN), defina OLLAMA_ALLOW_LAN=true."
                ),
            )
        # When LAN is allowed, still prevent loopback, link-local and metadata
        try:
            ip = ipaddress.ip_address(hostname)
            for net in [ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("0.0.0.0/8")]:
                if ip in net:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"SSRF Protection: Endereço '{ip}' proibido para Ollama.",
                    )
        except ValueError:
            _resolve_and_check_ips(hostname, allow_private=True)
        return cleaned_url

    # 3. Block literal localhost / loopback names explicitly for cloud providers
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSRF Protection: Endereços locais não são permitidos como base_url de provedor.",
        )

    # 4. Check official provider domain allowlist
    allowed_domains = OFFICIAL_PROVIDER_DOMAINS.get(provider_name)
    if allowed_domains and hostname not in allowed_domains:
        if not getattr(settings, "allow_custom_provider_urls", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"SSRF Protection: Domínio customizado '{hostname}' não é permitido para o provedor '{provider}'. "
                    f"Domínios autorizados: {', '.join(allowed_domains)}. "
                    "Para permitir endpoints customizados, defina ALLOW_CUSTOM_PROVIDER_URLS=true."
                ),
            )
        logger.warning(
            "Custom domain '%s' configured for provider '%s' (ALLOW_CUSTOM_PROVIDER_URLS habilitado)",
            hostname,
            provider,
        )

    # 5. Check if hostname is an IP literal or domain that resolves to private/reserved IP
    try:
        ip = ipaddress.ip_address(hostname)
        for net in BLOCKED_IP_NETWORKS:
            if ip in net:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SSRF Protection: Endereços IP privados ou reservados são proibidos.",
                )
    except ValueError:
        # Not a direct IP literal: resolve DNS to prevent DNS rebinding
        _resolve_and_check_ips(hostname, allow_private=False)

    return cleaned_url


import re

SENSITIVE_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_\-]{16,})", re.IGNORECASE),
    re.compile(r"(AIza[0-9A-Za-z\-_]{30,})", re.IGNORECASE),
    re.compile(r"(tp_live_[a-zA-Z0-9_\-]{16,})", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|secret|token|password|auth|cookie|set-cookie|proxy-authorization)[\"']?\s*[:=]\s*[\"']?)([^\s\"',&;]+)", re.IGNORECASE),
    re.compile(r"([?&](?:token|key|secret|password|apikey|api_key)=)([^&\s]+)", re.IGNORECASE),
]


def redact_sensitive_text(text: Optional[str]) -> Optional[str]:
    """Sanitizes sensitive API keys and tokens from strings and exception traces."""
    if not text:
        return text
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"[REDACTED]", redacted)
    return redacted


import time
from collections import defaultdict


class InMemoryRateLimiter:
    """
    Sliding-window rate limiter in memory (stdlib only, zero external dependencies).
    Limits requests per minute per key (e.g. client IP + provider).
    """

    def __init__(self, requests_per_minute: int = 120):
        self.rpm = requests_per_minute
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        if self.rpm <= 0:
            return True, 0
        now = time.time()
        window_start = now - 60.0
        # Filter timestamps within current 60s window
        history = [t for t in self._history[client_key] if t > window_start]
        if len(history) >= self.rpm:
            retry_after = int(60.0 - (now - history[0])) + 1
            return False, max(1, retry_after)
        history.append(now)
        self._history[client_key] = history
        return True, 0


gateway_rate_limiter = InMemoryRateLimiter(settings.gateway_rate_limit_rpm)


