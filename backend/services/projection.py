"""
services/projection.py — Calculation of burn rate, limit projections, and ETA.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional


def format_eta_minutes(minutes: float) -> str:
    """Format minutes into human readable string: e.g. 6h 45m or 2d 4h."""
    if minutes <= 0:
        return "Agora"
    
    total_mins = int(round(minutes))
    days = total_mins // 1440
    hours = (total_mins % 1440) // 60
    mins = total_mins % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0 or not parts:
        parts.append(f"{mins}m")
    
    return " ".join(parts)


def time_to_limit(current: int, limit: Optional[int], rate_per_hour: float) -> Optional[str]:
    """Calculate ETA in human readable format until limit is reached."""
    if not limit or limit <= 0 or rate_per_hour <= 0:
        return None
    
    remaining = limit - current
    if remaining <= 0:
        return "Limite atingido"
    
    hours_left = remaining / rate_per_hour
    minutes_left = hours_left * 60
    return format_eta_minutes(minutes_left)


def calculate_burn_rate(
    requests_today: int,
    tokens_today: int,
    cost_today: Optional[float],
    elapsed_hours_today: float,
    daily_request_limit: Optional[int] = None,
    daily_token_limit: Optional[int] = None,
) -> dict:
    """
    Calculate burn rate metrics and projections for the day.
    """
    hours = max(elapsed_hours_today, 0.1)  # Avoid division by zero
    
    req_per_hour = requests_today / hours
    tokens_per_hour = tokens_today / hours
    cost_per_hour = (cost_today / hours) if cost_today is not None else None

    # Extrapolate to full 24h
    projected_daily_requests = int(round(req_per_hour * 24))
    projected_daily_tokens = int(round(tokens_per_hour * 24))
    projected_daily_cost = round(cost_per_hour * 24, 4) if cost_per_hour is not None else None

    # Projected utilization %
    projected_req_pct = (
        round((projected_daily_requests / daily_request_limit) * 100, 1)
        if daily_request_limit
        else None
    )

    eta_requests = time_to_limit(requests_today, daily_request_limit, req_per_hour)
    eta_tokens = time_to_limit(tokens_today, daily_token_limit, tokens_per_hour)

    return {
        "requestsPerHour": round(req_per_hour, 1),
        "tokensPerHour": round(tokens_per_hour, 1),
        "costPerHour": round(cost_per_hour, 4) if cost_per_hour is not None else None,
        "projectedDailyRequests": projected_daily_requests,
        "projectedDailyTokens": projected_daily_tokens,
        "projectedDailyCost": projected_daily_cost,
        "projectedUtilizationPct": projected_req_pct,
        "etaRequestsLimit": eta_requests,
        "etaTokensLimit": eta_tokens,
    }
