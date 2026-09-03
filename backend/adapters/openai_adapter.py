"""
adapters/openai_adapter.py — OpenAI provider adapter.
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

# Models we consider "valid" OpenAI chat/completion models
_VALID_PREFIXES = ("gpt-", "o1", "o3", "text-embedding", "tts-", "whisper-", "dall-e")


def _lookup_pricing(model_id: str) -> tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    return lookup_pricing("openai", model_id)


class OpenAIAdapter(ProviderAdapter):
    """Adapter for the OpenAI REST API."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: Optional[str], base_url: Optional[str] = None):
        super().__init__(api_key, base_url or self.DEFAULT_BASE_URL)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=timeout,
        )

    async def get_models(self) -> list[ModelInfo]:
        """Fetch /models and return ModelInfo for relevant OpenAI models."""
        if not self.api_key:
            return []
        try:
            async with self._client() as client:
                resp = await client.get("/models")
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            logger.warning("OpenAI get_models timed out")
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("OpenAI get_models HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
            return []
        except Exception as exc:
            logger.error("OpenAI get_models error: %s", exc)
            return []

        models: list[ModelInfo] = []
        for m in data.get("data", []):
            model_id: str = m.get("id", "")
            # Keep only models that look like chat / completion models
            if not any(model_id.startswith(p) for p in _VALID_PREFIXES):
                continue
            inp, out, ctx, max_tok = _lookup_pricing(model_id)
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider="openai",
                    context_window=ctx,
                    max_tokens=max_tok,
                    input_price_per_1m=inp,
                    output_price_per_1m=out,
                    available=True,
                )
            )
        return models

    async def get_health(self) -> HealthStatus:
        """Probe GET /models with a short timeout to measure latency."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if not self.api_key:
            return HealthStatus(
                provider="openai",
                status="UNKNOWN",
                latency_ms=None,
                last_check=now_iso,
                details={"reason": "No API key configured"},
            )
        start = time.monotonic()
        try:
            async with self._client(timeout=5.0) as client:
                resp = await client.get("/models")
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                status = "ONLINE"
                details: dict = {}
            elif resp.status_code == 401:
                status = "OFFLINE"
                details = {"reason": "Authentication failed — check API key"}
            elif resp.status_code in (429, 503):
                status = "DEGRADED"
                details = {"reason": f"HTTP {resp.status_code}"}
            else:
                status = "DEGRADED"
                details = {"reason": f"Unexpected HTTP {resp.status_code}"}
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start) * 1000
            status = "OFFLINE"
            details = {"reason": "Request timed out"}
        except Exception as exc:
            latency_ms = None
            status = "UNKNOWN"
            details = {"reason": str(exc)}

        return HealthStatus(
            provider="openai",
            status=status,
            latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
            last_check=datetime.now(timezone.utc).isoformat(),
            details=details,
        )

    async def get_usage_summary(
        self, start_date: str, end_date: str
    ) -> list[NormalizedUsage]:
        """
        Try the Organization Usage endpoint (available on some tiers).
        Returns an empty list gracefully if the endpoint is not available.
        """
        if not self.api_key:
            return []
        try:
            async with self._client() as client:
                resp = await client.get(
                    "/organization/usage",
                    params={"start_date": start_date, "end_date": end_date},
                )
            if resp.status_code in (403, 404):
                # Not available on this tier
                logger.debug("OpenAI usage endpoint not available (HTTP %s)", resp.status_code)
                return []
            resp.raise_for_status()
            raw = resp.json()
        except httpx.HTTPStatusError:
            return []
        except Exception as exc:
            logger.warning("OpenAI get_usage_summary error: %s", exc)
            return []

        results: list[NormalizedUsage] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for bucket in raw.get("data", []):
            for result in bucket.get("results", []):
                model = result.get("model") or "unknown"
                inp_tok = result.get("input_tokens", 0)
                out_tok = result.get("output_tokens", 0)
                inp_price, out_price, _, _ = _lookup_pricing(model)
                cost_input = (inp_tok / 1_000_000 * inp_price) if inp_price else None
                cost_output = (out_tok / 1_000_000 * out_price) if out_price else None
                results.append(
                    NormalizedUsage(
                        provider="openai",
                        model=model,
                        timestamp=now_iso,
                        usage={
                            "requests": result.get("num_model_requests", 0),
                            "inputTokens": inp_tok,
                            "outputTokens": out_tok,
                            "totalTokens": inp_tok + out_tok,
                        },
                        limits={"daily": None, "weekly": None, "monthly": None, "rpm": None, "tpm": None},
                        performance={"latency": None, "p50": None, "p95": None, "p99": None},
                        errors={"total": None, "rate": None},
                        cost={
                            "input": round(cost_input, 6) if cost_input is not None else None,
                            "output": round(cost_output, 6) if cost_output is not None else None,
                            "total": round(cost_input + cost_output, 6) if (cost_input is not None and cost_output is not None) else None,
                            "currency": "USD",
                        },
                        raw=result,
                    )
                )
        return results
