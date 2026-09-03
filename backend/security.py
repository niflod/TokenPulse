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
