"""
services/webhook.py — Async Webhook Dispatcher for TokenPulse Alerts (Discord, Slack, Webhook).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def dispatch_alert_webhook(
    alert: Dict[str, Any],
    custom_url: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """
    Sends an alert notification to a webhook endpoint (Discord, Slack, or generic JSON).
    """
    webhook_url = custom_url or settings.alert_webhook_url
    if not webhook_url or not webhook_url.strip():
        return False

    from urllib.parse import urlparse
    import ipaddress
    from security import BLOCKED_IP_NETWORKS

    parsed = urlparse(webhook_url)
    if parsed.scheme.lower() not in ("http", "https"):
        logger.warning("Rejected webhook URL due to invalid scheme: %s", webhook_url)
        return False

    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        logger.warning("Rejected webhook URL due to loopback/empty address: %s", webhook_url)
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        for net in BLOCKED_IP_NETWORKS:
            if ip in net:
                logger.warning("SSRF Protection: Webhook address %s is in blocked network %s", ip, net)
                return False
    except ValueError:
        pass

    # Format payload (compatible with Discord, Slack, and generic webhooks)
    severity = alert.get("severity", "warning").upper()
    title = f"🚨 [TokenPulse Alert] {severity}: {alert.get('metric', 'Sistema')}"
    message = alert.get("message", "Limite ou anomalia detectada.")
    current_val = alert.get("currentValue", "N/A")
    threshold = alert.get("threshold", "N/A")
    provider = alert.get("provider", "all")

    # Discord & Slack & Generic JSON compatible payload
    payload = {
        "content": f"**{title}**\n{message}\n• **Provedor:** {provider}\n• **Valor Atual:** {current_val}\n• **Limite:** {threshold}",
        "text": f"{title}\n{message} (Provedor: {provider})",  # Slack fallback
        "event": "tokenpulse.alert",
        "alert": alert,
    }

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        own_client = True

    try:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code < 400:
            logger.info("Webhook alert dispatched successfully to %s", webhook_url)
            return True
        else:
            logger.warning("Webhook returned HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        logger.error("Failed to send alert webhook: %s", e)
        return False
    finally:
        if own_client:
            await client.aclose()
