"""
adapters/gemini_adapter.py — Google Gemini provider adapter.
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
    return lookup_pricing("gemini", model_id)


class GeminiAdapter(ProviderAdapter):
    """Adapter for Google Gemini REST API."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(self, api_key: Optional[str], base_url: Optional[str] = None):
        super().__init__(api_key, base_url or self.DEFAULT_BASE_URL)

    def _client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def get_models(self) -> list[ModelInfo]:
        """Fetch models from Google Generative Language API."""
        if not self.api_key:
            return []

        models: list[ModelInfo] = []
        try:
            async with self._client() as client:
                resp = await client.get("/v1beta/models", params={"key": self.api_key})
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("models", []):
                        m_name = m.get("name", "")  # e.g., "models/gemini-1.5-pro"
                        clean_id = m_name.replace("models/", "")
                        # Filter to gemini generative models
                        if "gemini" not in clean_id:
                            continue
                        inp, out, p_ctx, p_max = _lookup_pricing(clean_id)
                        ctx = m.get("inputTokenLimit", p_ctx or 1_000_000)
                        max_out = m.get("outputTokenLimit", p_max or 8192)
                        models.append(
                            ModelInfo(
                                id=clean_id,
                                name=m.get("displayName", clean_id),
                                provider="gemini",
                                context_window=ctx,
                                max_tokens=max_out,
                                input_price_per_1m=inp,
                                output_price_per_1m=out,
                                available=True,
                            )
                        )
                    if models:
                        return models
        except Exception as exc:
            logger.debug("Gemini get_models error: %s. Falling back to default list.", exc)

        # Fallback list if network/auth issues
        known = [
            ("gemini-2.0-flash", "Gemini 2.0 Flash", 1_048_576, 8192),
            ("gemini-1.5-pro", "Gemini 1.5 Pro", 2_097_152, 8192),
            ("gemini-1.5-flash", "Gemini 1.5 Flash", 1_048_576, 8192),
            ("gemini-1.5-flash-8b", "Gemini 1.5 Flash-8B", 1_048_576, 8192),
        ]
        for m_id, name, ctx, max_tok in known:
            inp, out, p_ctx, p_max = _lookup_pricing(m_id)
            models.append(
                ModelInfo(
                    id=m_id,
                    name=name,
                    provider="gemini",
                    context_window=p_ctx or ctx,
                    max_tokens=p_max or max_tok,
                    input_price_per_1m=inp,
                    output_price_per_1m=out,
                    available=True,
                )
            )
        return models

    async def get_health(self) -> HealthStatus:
        """Health check for Gemini API."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.api_key:
            return HealthStatus(
                provider="gemini",
                status="UNKNOWN",
                latency_ms=None,
                last_check=now_iso,
                details={"reason": "Nenhuma API Key configurada"},
            )

        start = time.monotonic()
        try:
            async with self._client(timeout=5.0) as client:
                resp = await client.get("/v1beta/models", params={"key": self.api_key, "pageSize": 1})
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                status = "ONLINE"
                details = {}
            elif resp.status_code in (400, 401, 403):
                status = "OFFLINE"
                details = {"reason": "Falha de autenticação ou chave inválida"}
            elif resp.status_code == 429:
                status = "DEGRADED"
                details = {"reason": "Quota ou Rate Limit excedido (429)"}
            else:
                status = "DEGRADED"
                details = {"reason": f"Status HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            status = "OFFLINE"
            details = {"reason": "Timeout de conexão"}
        except Exception as exc:
            latency_ms = None
            status = "UNKNOWN"
            details = {"reason": str(exc)}

        return HealthStatus(
            provider="gemini",
            status=status,
            latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
            last_check=datetime.now(timezone.utc).isoformat(),
            details=details,
        )

    async def get_usage_summary(
        self, start_date: str, end_date: str
    ) -> list[NormalizedUsage]:
        """Gemini does not have a usage query endpoint via standard API key."""
        return []
