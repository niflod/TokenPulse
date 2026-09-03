"""
adapters/base.py — Abstract base class and shared dataclasses for provider adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalizedUsage:
    """Unified usage data shape returned by all adapters."""

    provider: str
    model: str
    timestamp: str          # UTC ISO8601
    usage: dict             # requests, inputTokens, outputTokens, totalTokens
    limits: dict            # daily, weekly, monthly, rpm, tpm, rpd, tpd
    performance: dict       # latency, p50, p95, p99
    errors: dict            # total, rate
    cost: dict              # input, output, total, currency
    available: bool = True
    raw: dict = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Metadata and pricing for a single model."""

    id: str
    name: str
    provider: str
    context_window: Optional[int]
    max_tokens: Optional[int]
    input_price_per_1m: Optional[float]   # USD per 1 million input tokens
    output_price_per_1m: Optional[float]  # USD per 1 million output tokens
    available: bool = True


@dataclass
class HealthStatus:
    """Current health state of a provider's API."""

    provider: str
    status: str             # ONLINE | DEGRADED | OFFLINE | UNKNOWN
    latency_ms: Optional[float]
    last_check: str         # UTC ISO8601
    details: dict = field(default_factory=dict)


class ProviderAdapter(ABC):
    """
    Abstract base that every provider adapter must implement.
    Subclasses receive an optional API key and an optional base URL override.
    """

    def __init__(self, api_key: Optional[str], base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    async def get_models(self) -> list[ModelInfo]:
        """Return list of available models for this provider."""
        ...

    @abstractmethod
    async def get_health(self) -> HealthStatus:
        """Probe the provider API and return its health status."""
        ...

    @abstractmethod
    async def get_usage_summary(
        self, start_date: str, end_date: str
    ) -> list[NormalizedUsage]:
        """
        Fetch usage data for a date range (YYYY-MM-DD strings).
        Return empty list when the provider has no usage endpoint.
        """
        ...

    def calculate_cost(
        self, model_info: ModelInfo, input_tokens: int, output_tokens: int
    ) -> dict:
        """
        Calculate cost in USD from token counts and model pricing.
        Returns None values for all cost fields when pricing is unknown.
        """
        if model_info.input_price_per_1m is None:
            return {"input": None, "output": None, "total": None, "currency": "USD"}

        cost_input = (input_tokens / 1_000_000) * model_info.input_price_per_1m
        cost_output = (output_tokens / 1_000_000) * (model_info.output_price_per_1m or 0.0)
        return {
            "input": round(cost_input, 6),
            "output": round(cost_output, 6),
            "total": round(cost_input + cost_output, 6),
            "currency": "USD",
        }
