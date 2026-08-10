"""Executive Dashboard -- headline KPIs, trend, region mix, and AI insight band."""
from __future__ import annotations

import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_inr, format_number, format_pct, delta_string
from utils.filters import render_filter_panel
from utils.ai_insights import generate_executive_summary
from charts.plotly_charts import line_chart, bar_chart, pie_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("📊 Executive Dashboard")
st.caption("Company-wide performance overview for CEO / CFO / CRO audiences.")

db = DatabaseManager()
filters = render_filter_panel(db, key_prefix="exec", fields=["Region", "Year", "Channel"])

kpis = db.get_kpi_summary(filters)
yearly = db.get_trend("Year", filters)
monthly = db.get_trend("Month", filters)
regions = db.get_sales_by_dimension("Region", filters)

prev_rev = yearly.iloc[-2]["Net_Revenue"] if len(yearly) >= 2 else None
rev_delta, rev_sent = delta_string(kpis["total_revenue"], prev_rev, "YoY") if prev_rev else ("n/a", "neutral")
prev_profit = yearly.iloc[-2]["Profit"] if len(yearly) >= 2 else None
profit_delta, profit_sent = delta_string(kpis["total_profit"], prev_profit, "YoY") if prev_profit else ("n/a", "neutral")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(kpi_card_html("Net Revenue", format_inr(kpis["total_revenue"]), rev_delta, rev_sent), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card_html("Total Profit", format_inr(kpis["total_profit"]), profit_delta, profit_sent), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card_html("Profit Margin", format_pct(kpis["profit_margin_pct"]), sentiment="neutral"), unsafe_allow_html=True)
with c4:
    st.markdown(kpi_card_html("Avg Order Value", format_inr(kpis["avg_order_value"]), sentiment="neutral"), unsafe_allow_html=True)

c5, c6, c7, c8 = st.columns(4)
with c5:
    st.markdown(kpi_card_html("Total Orders", format_number(kpis["total_orders"])), unsafe_allow_html=True)
with c6:
    st.markdown(kpi_card_html("Total Customers", format_number(kpis["total_customers"])), unsafe_allow_html=True)
with c7:
    st.markdown(kpi_card_html("Total Products", format_number(kpis["total_products"])), unsafe_allow_html=True)
with c8:
    sentiment = "neg" if kpis["return_rate_pct"] > 8 else "neutral"
    st.markdown(kpi_card_html("Return Rate", format_pct(kpis["return_rate_pct"]), sentiment=sentiment), unsafe_allow_html=True)

st.markdown("### 🤖 AI-Generated Insights")
insights = generate_executive_summary(db, filters)
for line in insights:
    st.markdown(f'<div class="insight-band">💡 {line}</div>', unsafe_allow_html=True)

st.markdown("---")
col_left, col_right = st.columns([1.4, 1])
with col_left:
    st.markdown('<div class="section-title">Net Revenue Trend</div>', unsafe_allow_html=True)
    if not monthly.empty:
        monthly["Period"] = monthly["Year"].astype(str) + "-" + monthly["Month"].astype(str).str.zfill(2)
        st.plotly_chart(line_chart(monthly, "Period", "Net_Revenue"), use_container_width=True)
    else:
        st.info("No data for the selected filters.")
with col_right:
    st.markdown('<div class="section-title">Revenue by Region</div>', unsafe_allow_html=True)
    if not regions.empty:
        st.plotly_chart(pie_chart(regions, "Region", "Net_Revenue"), use_container_width=True)
    else:
        st.info("No data for the selected filters.")

st.markdown('<div class="section-title">Yearly Revenue vs Profit</div>', unsafe_allow_html=True)
if not yearly.empty:
    st.plotly_chart(bar_chart(yearly, "Year", "Net_Revenue"), use_container_width=True)
