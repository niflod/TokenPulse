"""
adapters/anthropic_adapter.py — Anthropic provider adapter.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from adapters.base import HealthStatus, ModelInfo, NormalizedUsage, ProviderAdapter

logger = logging.getLogger(__name__)

from pricing import lookup_pricing


def _lookup_pricing(model_id: str) -> tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    return lookup_pricing("anthropic", model_id)


class AnthropicAdapter(ProviderAdapter):
    """Adapter for Anthropic API (Claude models)."""

    DEFAULT_BASE_URL = "https://api.anthropic.com/v1"

    def __init__(self, api_key: Optional[str], base_url: Optional[str] = None):
        super().__init__(api_key, base_url or self.DEFAULT_BASE_URL)

    def _headers(self) -> dict:
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=timeout,
        )

    async def get_models(self) -> list[ModelInfo]:
        """Query Anthropic models list or return known models if unauthorized."""
        models: list[ModelInfo] = []
        
        if not self.api_key:
            return []

        try:
            async with self._client() as client:
                resp = await client.get("/models")
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("data", []):
                        m_id = m.get("id", "")
                        inp, out, p_ctx, p_max = _lookup_pricing(m_id)
                        models.append(
                            ModelInfo(
                                id=m_id,
                                name=m.get("display_name", m_id),
                                provider="anthropic",
                                context_window=p_ctx or 200_000,
                                max_tokens=p_max or (8192 if "3-5" in m_id else 4096),
                                input_price_per_1m=inp,
                                output_price_per_1m=out,
                                available=True,
                            )
                        )
                    if models:
                        return models
        except Exception as exc:
            logger.debug("Anthropic /models call error: %s. Falling back to known models list.", exc)

        # Known standard models fallback
        known = [
            ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet", 200_000, 8192),
            ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku", 200_000, 8192),
            ("claude-3-opus-20240229", "Claude 3 Opus", 200_000, 4096),
            ("claude-3-haiku-20240307", "Claude 3 Haiku", 200_000, 4096),
        ]
        for m_id, name, ctx, max_tok in known:
            inp, out, p_ctx, p_max = _lookup_pricing(m_id)
            models.append(
                ModelInfo(
                    id=m_id,
                    name=name,
                    provider="anthropic",
                    context_window=p_ctx or ctx,
                    max_tokens=p_max or max_tok,
                    input_price_per_1m=inp,
                    output_price_per_1m=out,
                    available=True,
                )
            )
        return models

    async def get_health(self) -> HealthStatus:
        """Health check for Anthropic API."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.api_key:
            return HealthStatus(
                provider="anthropic",
                status="UNKNOWN",
                latency_ms=None,
                last_check=now_iso,
                details={"reason": "Nenhuma API Key configurada"},
            )

        start = time.monotonic()
        try:
            async with self._client(timeout=5.0) as client:
                resp = await client.get("/models")
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                status = "ONLINE"
                details = {}
            elif resp.status_code == 401:
                status = "OFFLINE"
                details = {"reason": "Falha de autenticação (401)"}
            elif resp.status_code in (429, 529, 503):
                status = "DEGRADED"
                details = {"reason": f"Rate limit / sobrecarga (HTTP {resp.status_code})"}
            else:
                status = "DEGRADED"
                details = {"reason": f"Status HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            status = "OFFLINE"
            details = {"reason": "Timeout na requisição"}
        except Exception as exc:
            latency_ms = None
            status = "UNKNOWN"
            details = {"reason": str(exc)}

        return HealthStatus(
            provider="anthropic",
            status=status,
            latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
            last_check=datetime.now(timezone.utc).isoformat(),
            details=details,
        )

    async def get_usage_summary(
        self, start_date: str, end_date: str
    ) -> list[NormalizedUsage]:
        """Anthropic does not expose a historical usage API; usage is tracked via proxy logs."""
        return []
