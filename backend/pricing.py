"""
pricing.py — Centralized model catalog, pricing registry and token limit metadata.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Official pricing catalog (USD per 1M tokens)
# Format: {provider: {model_prefix: (input_price_per_1m, output_price_per_1m, context_window, max_output)}}
MODEL_PRICING_CATALOG: Dict[str, Dict[str, Tuple[float, float, int, int]]] = {
    "openai": {
        "gpt-4o-mini": (0.15, 0.60, 128_000, 16_384),
        "gpt-4o": (2.50, 10.00, 128_000, 16_384),
        "gpt-4-turbo": (10.00, 30.00, 128_000, 4_096),
        "gpt-4": (30.00, 60.00, 8_192, 4_096),
        "gpt-3.5-turbo": (0.50, 1.50, 16_385, 4_096),
        "o1-mini": (3.00, 12.00, 128_000, 65_536),
        "o1-preview": (15.00, 60.00, 128_000, 32_768),
        "o1": (15.00, 60.00, 200_000, 100_000),
        "o3-mini": (1.10, 4.40, 200_000, 100_000),
        "o3": (10.00, 40.00, 200_000, 100_000),
    },
    "anthropic": {
        "claude-3-5-sonnet": (3.00, 15.00, 200_000, 8_192),
        "claude-3-5-haiku": (0.80, 4.00, 200_000, 8_192),
        "claude-3-opus": (15.00, 75.00, 200_000, 4_096),
        "claude-3-sonnet": (3.00, 15.00, 200_000, 4_096),
        "claude-3-haiku": (0.25, 1.25, 200_000, 4_096),
        "claude-opus-4": (15.00, 75.00, 200_000, 8_192),
        "claude-sonnet-4": (3.00, 15.00, 200_000, 8_192),
    },
    "gemini": {
        "gemini-2.5-pro": (1.25, 10.00, 2_000_000, 8_192),
        "gemini-2.5-flash": (0.30, 2.50, 1_000_000, 8_192),
        "gemini-2.0-flash": (0.10, 0.40, 1_048_576, 8_192),
        "gemini-1.5-pro": (1.25, 5.00, 2_097_152, 8_192),
        "gemini-1.5-flash-8b": (0.0375, 0.15, 1_048_576, 8_192),
        "gemini-1.5-flash": (0.075, 0.30, 1_048_576, 8_192),
        "gemini-1.0-pro": (0.50, 1.50, 32_768, 8_192),
    },
}


def lookup_pricing(
    provider: str, model_id: str
) -> Tuple[Optional[float], Optional[float], Optional[int], Optional[int]]:
    """
    Looks up pricing and context limits by longest prefix match.
    Returns: (input_price_1m, output_price_1m, context_window, max_tokens)
    """
    provider_key = provider.lower().strip()
    clean_id = model_id.replace("models/", "").lower().strip()

    catalog = MODEL_PRICING_CATALOG.get(provider_key, {})
    best_key = None

    for prefix in catalog:
        if clean_id.startswith(prefix):
            if best_key is None or len(prefix) > len(best_key):
                best_key = prefix

    if best_key:
        return catalog[best_key]

    return None, None, None, None
