"""Shared formatting helpers used across every page."""
from __future__ import annotations

from typing import Optional

import pandas as pd


def format_inr(value: float, decimals: int = 2) -> str:
    """Format a raw rupee value into Indian Crore/Lakh notation.

    Args:
        value: Raw rupee amount.
        decimals: Decimal places to show.

    Returns:
        A string like "₹560.37 Cr" or "₹12.40 L" or "₹8,500.00" for
        small values below one lakh.
    """
    if value is None or pd.isna(value):
        return "₹0.00"
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 1_00_00_000:  # 1 Crore
        return f"{sign}₹{abs_value / 1_00_00_000:.{decimals}f} Cr"
    if abs_value >= 1_00_000:  # 1 Lakh
        return f"{sign}₹{abs_value / 1_00_000:.{decimals}f} L"
    return f"{sign}₹{abs_value:,.{decimals}f}"


def format_number(value: float, decimals: int = 0) -> str:
    """Format a plain count/number with thousands separators."""
    if value is None or pd.isna(value):
        return "0"
    return f"{value:,.{decimals}f}"


def format_pct(value: float, decimals: int = 2) -> str:
    """Format a percentage value (already scaled 0-100)."""
    if value is None or pd.isna(value):
        return "0.00%"
    return f"{value:.{decimals}f}%"


def delta_string(current: float, previous: float, suffix: str = "") -> tuple[str, str]:
    """Compute a delta string and sentiment class for a KPI card.

    Returns:
        (delta_text, sentiment) where sentiment is "pos" or "neg".
    """
    if previous in (None, 0) or pd.isna(previous):
        return "n/a", "neutral"
    pct_change = 100.0 * (current - previous) / previous
    arrow = "▲" if pct_change >= 0 else "▼"
    sentiment = "pos" if pct_change >= 0 else "neg"
    return f"{arrow} {abs(pct_change):.1f}% {suffix}".strip(), sentiment


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide two numbers, returning ``default`` instead of raising on zero division."""
    try:
        if denominator in (0, None) or pd.isna(denominator):
            return default
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return default


def month_number_to_name(month: int) -> str:
    """Convert a 1-12 month integer into its short name."""
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        return names[int(month) - 1]
    except (IndexError, ValueError, TypeError):
        return str(month)


def none_if_all(value: Optional[str]) -> Optional[str]:
    """Normalize a selectbox's 'All' sentinel value to None for query building."""
    return None if value in (None, "All", "") else value
