"""
Lightweight natural-language query (NLQ) parser.

Honesty note: this is a regex/keyword-based intent parser, not an LLM. It
recognizes a defined vocabulary (metrics, regions, quarters, years,
categories) in a typed sentence and converts it into a structured filter +
metric request that the DatabaseManager can execute. This keeps the
"ask a question in plain English" feature working with zero API keys and
zero network dependency -- see README for how to swap in a real LLM if an
OpenAI key is configured.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from utils.database import DatabaseManager

_METRIC_KEYWORDS: dict[str, list[str]] = {
    "Return_Rate": ["return rate", "returns", "returned"],
    "Net_Revenue": ["revenue", "sales", "sale"],
    "Profit": ["profit", "margin", "profitability"],
    "Orders": ["orders", "order count", "transactions"],
    "Units": ["units", "quantity", "volume"],
}

_QUARTER_PATTERN = re.compile(r"\bq([1-4])\b", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


@dataclass
class ParsedQuery:
    """Structured result of parsing a natural-language question."""
    metric: str = "Net_Revenue"
    dimension: Optional[str] = None       # dimension to group by, if the question implies a breakdown
    filters: dict[str, Any] = field(default_factory=dict)
    recognized_terms: list[str] = field(default_factory=list)
    raw_text: str = ""


class NaturalLanguageQueryEngine:
    """Parses a plain-English sales question into a filtered query and answer."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        options = db.get_filter_options()
        self._regions = {str(v).lower(): v for v in options.get("Region", [])}
        self._categories = {str(v).lower(): v for v in options.get("Category", [])}
        self._channels = {str(v).lower(): v for v in options.get("Channel", [])}
        self._segments = {str(v).lower(): v for v in options.get("Segment", [])}

    def parse(self, text: str) -> ParsedQuery:
        """Extract metric, filters, and an optional breakdown dimension from free text."""
        lower = text.lower()
        result = ParsedQuery(raw_text=text)

        for metric, keywords in _METRIC_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                result.metric = metric
                result.recognized_terms.append(metric)
                break

        for key, value in self._regions.items():
            if key in lower:
                result.filters["Region"] = value
                result.recognized_terms.append(f"Region={value}")
                break

        for key, value in self._categories.items():
            if key in lower:
                result.filters["Category"] = value
                result.recognized_terms.append(f"Category={value}")
                break

        for key, value in self._channels.items():
            if key in lower:
                result.filters["Channel"] = value
                result.recognized_terms.append(f"Channel={value}")
                break

        for key, value in self._segments.items():
            if key in lower:
                result.filters["Segment"] = value
                result.recognized_terms.append(f"Segment={value}")
                break

        q_match = _QUARTER_PATTERN.search(lower)
        if q_match:
            result.filters["Quarter"] = f"Q{q_match.group(1)}"
            result.recognized_terms.append(f"Quarter=Q{q_match.group(1)}")

        y_match = _YEAR_PATTERN.search(lower)
        if y_match:
            result.filters["Year"] = int(y_match.group(1))
            result.recognized_terms.append(f"Year={y_match.group(1)}")

        for name, num in _MONTH_NAMES.items():
            if name in lower:
                result.filters["Month"] = num
                result.recognized_terms.append(f"Month={name.title()}")
                break

        if any(w in lower for w in ["by region", "per region", "across regions", "each region"]):
            result.dimension = "Region"
        elif any(w in lower for w in ["by category", "per category", "each category"]):
            result.dimension = "Category"
        elif any(w in lower for w in ["by product", "per product", "top product"]):
            result.dimension = "Product"
        elif any(w in lower for w in ["by customer", "top customer"]):
            result.dimension = "Customer"
        elif any(w in lower for w in ["by salesperson", "sales rep", "each rep"]):
            result.dimension = "Salesperson"

        return result

    def answer(self, text: str) -> tuple[str, pd.DataFrame]:
        """Parse a question and return (plain-English answer, supporting DataFrame).

        Args:
            text: A free-text question, e.g. "Show revenue in the South
                region for Q2 2025" or "Top products by profit in Electronics".

        Returns:
            A tuple of a natural-language answer sentence and the DataFrame
            backing it (for optional chart/table display).
        """
        parsed = self.parse(text)

        # get_sales_by_dimension() only aggregates these four metrics --
        # Return_Rate isn't a plain SUM the same way (it's a ratio), so it
        # has no column there. Attempting "ORDER BY Return_Rate DESC"
        # against that query raises a real SQL error. If a question asks
        # for a per-dimension breakdown of a metric that can't be broken
        # down this way, fall through to the overall-KPI answer below
        # instead of crashing.
        _DIMENSION_BREAKDOWN_METRICS = {"Net_Revenue", "Profit", "Orders", "Units"}
        if parsed.dimension and parsed.metric in _DIMENSION_BREAKDOWN_METRICS:
            df = self.db.get_sales_by_dimension(parsed.dimension, parsed.filters, metric=parsed.metric)
            if df.empty:
                return "No matching data was found for that question.", df
            top_row = df.iloc[0]
            metric_label = parsed.metric.replace("_", " ")
            filt_desc = ", ".join(f"{k}={v}" for k, v in parsed.filters.items()) or "all data"
            answer = (
                f"Breakdown by {parsed.dimension} for {filt_desc}: "
                f"**{top_row[parsed.dimension if parsed.dimension in df.columns else df.columns[0]]}** "
                f"leads with {metric_label} of {top_row.get(parsed.metric, top_row.iloc[1]):,.0f}."
            )
            return answer, df

        dimension_was_dropped = bool(parsed.dimension) and parsed.metric not in _DIMENSION_BREAKDOWN_METRICS

        kpis = self.db.get_kpi_summary(parsed.filters)
        metric_map = {
            "Net_Revenue": ("total_revenue", "net revenue", False),
            "Profit": ("total_profit", "total profit", False),
            "Orders": ("total_orders", "total orders", False),
            "Units": ("total_line_items", "total line items", False),
            "Return_Rate": ("return_rate_pct", "return rate", True),
        }
        field_name, label, is_pct = metric_map.get(parsed.metric, ("total_revenue", "net revenue", False))
        value = kpis.get(field_name, 0)
        filt_desc = ", ".join(f"{k}={v}" for k, v in parsed.filters.items()) or "across all data"
        value_str = f"{value:.2f}%" if is_pct else f"{value:,.0f}"
        answer = f"The {label} for {filt_desc} is **{value_str}**."
        if dimension_was_dropped:
            answer += f" (A per-{parsed.dimension} breakdown isn't available for {label}, so this is the overall figure.)"
        return answer, pd.DataFrame([kpis])
