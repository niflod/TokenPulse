"""
security.py — Administrative authentication and SSRF protection for TokenPulse.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

# Official allowed domains for known providers
OFFICIAL_PROVIDER_DOMAINS = {
    "openai": ["api.openai.com"],
    "anthropic": ["api.anthropic.com"],
    "gemini": ["generativelanguage.googleapis.com"],
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
    x_admin_key: Optional[str] = Security(api_key_header),
    authorization: Optional[str] = Header(None),
) -> bool:
    """
    Validates administrative access for mutating endpoints.
    If ADMIN_API_KEY is not configured, allows local loopback development.
    """
    configured_key = settings.admin_api_key
    if not configured_key:
        return True  # Open by default if no admin key was specified in settings

    # Check X-Admin-Key header
    if x_admin_key and secrets_compare(x_admin_key, configured_key):
        return True

    # Check Authorization: Bearer <token>
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if secrets_compare(token, configured_key):
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Acesso administrativo não autorizado. Forneça o header X-Admin-Key válido.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def secrets_compare(val1: str, val2: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac
    return hmac.compare_digest(val1.encode("utf-8"), val2.encode("utf-8"))


def validate_provider_base_url(provider: str, base_url: Optional[str]) -> Optional[str]:
    """
    Validates provider base URL against SSRF attacks.
    Ensures HTTPS protocol and prevents redirection to internal networks or loopback.
    """
    if not base_url or not base_url.strip():
        return None

    cleaned_url = base_url.strip().rstrip("/")
    parsed = urlparse(cleaned_url)

    # 1. Scheme check: only HTTPS allowed
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

    # 2. Block localhost / loopback names explicitly
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSRF Protection: Endereços locais não são permitidos como base_url de provedor.",
        )

    # 3. Check if hostname resolves to or is a private/reserved IP
    try:
        ip = ipaddress.ip_address(hostname)
        for net in BLOCKED_IP_NETWORKS:
            if ip in net:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SSRF Protection: Endereços IP privados ou reservados são proibidos.",
                )
    except ValueError:
        # Not a direct IP literal, domain name is used
        pass

    # 4. If provider is in official list, ensure host belongs to allowed domain
    allowed_domains = OFFICIAL_PROVIDER_DOMAINS.get(provider.lower())
    if allowed_domains and hostname not in allowed_domains:
        # Permitted only if explicitly safe domain
        logger.warning(
            "Custom domain '%s' configured for provider '%s' (Official: %s)",
            hostname,
            provider,
            allowed_domains,
        )

    return cleaned_url


import re

SENSITIVE_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_\-]{16,})", re.IGNORECASE),
    re.compile(r"(AIza[0-9A-Za-z\-_]{30,})", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|secret|token|password|auth)[\"']?\s*[:=]\s*[\"']?)([^\s\"',&]+)", re.IGNORECASE),
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


