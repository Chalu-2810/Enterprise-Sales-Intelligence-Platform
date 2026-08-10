"""
Tests for DatabaseManager's KPI/aggregation methods, using the synthetic
star-schema fixture from conftest.py. All expected values below are
hand-calculated from the fixture's raw rows -- see conftest.py's
_FACT_SALES for the source data, or the per-test docstrings for the worked
arithmetic.

Net_Revenue = Sales_Amount - Discount_Amount, per fixture row:
    Row1 (Alice/North/WidgetA):  200-20  = 180
    Row2 (Bob/South/WidgetB):    150-0   = 150
    Row3 (Alice/North/WidgetA):  100-10  =  90
    Row4 (Bob/South/WidgetB):    450-45  = 405
"""
from __future__ import annotations

import pytest

from utils.database import DatabaseManager


@pytest.fixture
def db(patched_engine) -> DatabaseManager:
    return DatabaseManager()


def test_kpi_summary_totals(db):
    """Total Net_Revenue = 180+150+90+405 = 825; Total Profit = 80+70+40+165 = 355."""
    kpis = db.get_kpi_summary()
    assert kpis["total_revenue"] == 825
    assert kpis["total_profit"] == 355
    assert kpis["total_orders"] == 4
    assert kpis["total_customers"] == 2
    assert kpis["total_products"] == 2
    assert kpis["returned_orders"] == 1
    assert kpis["total_line_items"] == 4


def test_kpi_summary_derived_metrics(db):
    kpis = db.get_kpi_summary()
    assert kpis["profit_margin_pct"] == pytest.approx(100.0 * 355 / 825)
    assert kpis["avg_order_value"] == pytest.approx(825 / 4)
    assert kpis["return_rate_pct"] == pytest.approx(100.0 * 1 / 4)


def test_kpi_summary_with_filter_applied(db):
    """Filtering to North region should only include Alice's two rows (180+90=270)."""
    kpis = db.get_kpi_summary(filters={"Region": "North"})
    assert kpis["total_revenue"] == 270
    assert kpis["total_orders"] == 2
    assert kpis["total_customers"] == 1


def test_kpi_summary_with_filter_matching_nothing_returns_zeros(db):
    kpis = db.get_kpi_summary(filters={"Region": "Nonexistent"})
    assert kpis["total_revenue"] == 0
    assert kpis["total_orders"] == 0
    assert kpis["profit_margin_pct"] == 0.0  # must not divide by zero


def test_sales_by_dimension_region_grouping_and_order(db):
    """South (Bob) = 150+405=555 net revenue; North (Alice) = 180+90=270.
    Default ORDER BY Net_Revenue DESC -> South first."""
    result = db.get_sales_by_dimension("Region")
    assert list(result["Region"]) == ["South", "North"]
    assert list(result["Net_Revenue"]) == [555, 270]


def test_trend_by_year_aggregates_all_rows(db):
    """All 4 fixture rows fall in 2024 -> single trend row with the full totals."""
    result = db.get_trend(grain="Year")
    assert len(result) == 1
    assert result.iloc[0]["Year"] == 2024
    assert result.iloc[0]["Net_Revenue"] == 825
    assert result.iloc[0]["Orders"] == 4


def test_top_customers_ranked_by_net_revenue(db):
    """Bob (555) outranks Alice (270)."""
    result = db.get_top_customers(n=10)
    assert list(result["Customer"]) == ["Bob", "Alice"]
    assert list(result["Net_Revenue"]) == [555, 270]


def test_top_products_ranked_by_net_revenue(db):
    """Widget B (555) outranks Widget A (270)."""
    result = db.get_top_products(n=10)
    assert list(result["Product"]) == ["Widget B", "Widget A"]


def test_top_products_ascending_flips_order(db):
    result = db.get_top_products(n=10, ascending=True)
    assert list(result["Product"]) == ["Widget A", "Widget B"]


def test_abc_analysis_classification(db):
    """Widget B is 555/825 = 67.3% of cumulative revenue -> Class A.
    Widget A brings cumulative to 100% -> Class C (crosses the 90% line)."""
    result = db.get_abc_analysis()
    by_product = result.set_index("Product")
    assert by_product.loc["Widget B", "ABC_Class"] == "A"
    assert by_product.loc["Widget A", "ABC_Class"] == "C"


def test_abc_analysis_on_empty_result_does_not_crash(db):
    result = db.get_abc_analysis(filters={"Region": "Nonexistent"})
    assert result.empty
