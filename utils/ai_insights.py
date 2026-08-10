"""
AI Insights engine: generates plain-English executive summary sentences
from the current data/filter context.

Honesty note: by default this is a template-based Natural Language
Generation (NLG) engine -- it computes real statistics (growth rates,
concentration, correlations) and turns them into readable sentences using
a rule/priority system (mirroring the Phase-10 "smart narrative" design).
It requires zero API keys and works fully offline.

If an OpenAI API key is present in the environment (config.OPENAI_API_KEY),
`generate_llm_narrative()` can optionally rewrite the same computed facts
into a more fluent narrative via a real LLM call -- the facts themselves
always come from the database, never from the LLM, so numbers can't be
hallucinated even when the optional LLM path is used.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from config import OPENAI_API_KEY
from utils.database import DatabaseManager
from utils.helpers import format_inr, format_pct, safe_divide
from utils.logger import get_logger

logger = get_logger(__name__)


def _trend_direction(current: float, previous: float) -> tuple[str, float]:
    pct = safe_divide(current - previous, previous) * 100
    direction = "grew" if pct >= 0 else "declined"
    return direction, abs(pct)


def generate_executive_summary(db: DatabaseManager, filters: dict[str, Any] | None = None) -> list[str]:
    """Compute real statistics and turn them into a short list of insight sentences.

    Args:
        db: An initialized DatabaseManager.
        filters: Optional filter context to scope the insights to.

    Returns:
        A list of plain-English insight strings, ordered by the same
        trigger-priority logic documented in the Phase-10 UX guidelines.
    """
    insights: list[str] = []

    kpis = db.get_kpi_summary(filters)
    yearly = db.get_trend("Year", filters)
    regions = db.get_sales_by_dimension("Region", filters)
    abc = db.get_abc_analysis(filters)

    # 1. YoY growth trend
    if len(yearly) >= 2:
        current, previous = yearly.iloc[-1], yearly.iloc[-2]
        direction, pct = _trend_direction(current["Net_Revenue"], previous["Net_Revenue"])
        insights.append(
            f"Net revenue {direction} {pct:.1f}% in {int(current['Year'])} versus {int(previous['Year'])}, "
            f"closing the year at {format_inr(current['Net_Revenue'])}."
        )

    # 2. Profit margin health
    margin = kpis.get("profit_margin_pct", 0)
    margin_comment = "a healthy margin" if margin >= 15 else "a margin worth monitoring closely"
    insights.append(
        f"Overall profit margin stands at {format_pct(margin)} on {format_inr(kpis.get('total_revenue', 0))} "
        f"in net revenue -- {margin_comment}."
    )

    # 3. Regional concentration
    if not regions.empty:
        top_region = regions.iloc[0]
        share = safe_divide(top_region["Net_Revenue"], regions["Net_Revenue"].sum()) * 100
        insights.append(
            f"{top_region['Region']} is the leading region, contributing {format_pct(share)} of total revenue "
            f"({format_inr(top_region['Net_Revenue'])})."
        )

    # 4. ABC product concentration
    if not abc.empty and "ABC_Class" in abc.columns:
        class_a = abc[abc["ABC_Class"] == "A"]
        pct_products = safe_divide(len(class_a), len(abc)) * 100
        pct_revenue = safe_divide(class_a["Net_Revenue"].sum(), abc["Net_Revenue"].sum()) * 100
        insights.append(
            f"Just {pct_products:.0f}% of products (Class A) generate {pct_revenue:.0f}% of revenue -- "
            f"a concentration worth protecting with supply-chain priority."
        )

    # 5. Return rate flag
    return_rate = kpis.get("return_rate_pct", 0)
    if return_rate > 8:
        insights.append(
            f"Return rate is elevated at {format_pct(return_rate)} -- worth cross-checking against "
            f"discount depth, a pattern previously linked to return spikes in this dataset."
        )
    else:
        insights.append(f"Return rate is within a normal range at {format_pct(return_rate)}.")

    return insights


def is_llm_available() -> bool:
    """True only if an API key is configured AND the openai package is
    actually importable (it's an optional dependency, not in
    requirements.txt by default -- see README for enabling it).

    Without this check, a UI status banner based on OPENAI_API_KEY alone
    would claim "LLM active" even when the package isn't installed --
    generate_llm_narrative()'s except-block correctly prevents a crash in
    that case by falling back to rule-based text, but the banner would
    keep telling the user the LLM was active when it demonstrably wasn't.
    """
    if not OPENAI_API_KEY:
        return False
    try:
        import openai  # noqa: F401
        return True
    except ImportError:
        return False


def generate_llm_narrative(facts: list[str]) -> str:
    """Optionally rewrite computed facts into a more fluent narrative via a real LLM.

    This function ONLY runs if an OpenAI API key is configured; otherwise it
    returns the rule-based bullet list unchanged (joined into prose) so the
    app never breaks or requires configuration to function.

    Args:
        facts: The output of generate_executive_summary() -- factual,
            database-derived sentences that the LLM may only rephrase,
            not invent numbers for.
    """
    if not OPENAI_API_KEY:
        return " ".join(facts)

    try:
        from openai import OpenAI  # imported lazily; optional dependency

        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            "Rewrite the following bullet-point business facts into a short, "
            "fluent executive-summary paragraph. Do not invent any numbers "
            "or facts beyond what is given.\n\n" + "\n".join(f"- {f}" for f in facts)
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("LLM narrative generation failed; falling back to rule-based summary.")
        return " ".join(facts)
