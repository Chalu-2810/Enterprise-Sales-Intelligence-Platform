"""Customer Analytics -- CLV, top customers, segment comparison, retention."""
from __future__ import annotations

import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_inr, format_number, format_pct
from utils.filters import render_filter_panel
from charts.plotly_charts import bar_chart, pie_chart, scatter_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("👥 Customer Analytics")
st.caption("Customer value, segmentation, and retention signals.")

db = DatabaseManager()
filters = render_filter_panel(db, key_prefix="cust", fields=["Region", "Segment", "Year"])

kpis = db.get_kpi_summary(filters)
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(kpi_card_html("Total Customers", format_number(kpis["total_customers"])), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card_html("Avg Order Value", format_inr(kpis["avg_order_value"])), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card_html("Net Revenue", format_inr(kpis["total_revenue"])), unsafe_allow_html=True)
with c4:
    revenue_per_cust = kpis["total_revenue"] / kpis["total_customers"] if kpis["total_customers"] else 0
    st.markdown(kpi_card_html("Revenue / Customer", format_inr(revenue_per_cust)), unsafe_allow_html=True)

tab_top, tab_segment, tab_pareto = st.tabs(["🏆 Top Customers", "🧩 Segment Comparison", "📐 Revenue Concentration"])

with tab_top:
    n = st.slider("Show top N customers", 5, 50, 10, key="cust_top_n")
    top_customers = db.get_top_customers(n, filters)
    if not top_customers.empty:
        st.plotly_chart(bar_chart(top_customers, "Customer", "Net_Revenue", f"Top {n} Customers by Net Revenue"),
                         use_container_width=True)
        st.dataframe(top_customers, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")

with tab_segment:
    seg_df = db.get_sales_by_dimension("Segment", filters)
    col1, col2 = st.columns(2)
    with col1:
        if not seg_df.empty:
            st.plotly_chart(pie_chart(seg_df, "Segment", "Net_Revenue", "Revenue Share by Segment"),
                             use_container_width=True)
    with col2:
        if not seg_df.empty:
            seg_df_display = seg_df.copy()
            seg_df_display["Avg_Order_Value"] = (seg_df_display["Net_Revenue"] / seg_df_display["Orders"]).round(0)
            st.plotly_chart(bar_chart(seg_df_display, "Segment", "Avg_Order_Value", "Avg Order Value by Segment"),
                             use_container_width=True)
    st.dataframe(seg_df, use_container_width=True, hide_index=True)

with tab_pareto:
    top_customers_full = db.get_top_customers(n=10_000, filters=filters).sort_values("Net_Revenue", ascending=False)
    if not top_customers_full.empty:
        top_customers_full = top_customers_full.reset_index(drop=True)
        top_customers_full["Cumulative_Pct"] = (
            100 * top_customers_full["Net_Revenue"].cumsum() / top_customers_full["Net_Revenue"].sum()
        )
        top20_cutoff = int(len(top_customers_full) * 0.2)
        top20_share = top_customers_full.iloc[:top20_cutoff]["Net_Revenue"].sum() / top_customers_full["Net_Revenue"].sum() * 100
        st.metric("Top 20% of Customers' Revenue Share", format_pct(top20_share))
        top_customers_full["Customer_Rank_Pct"] = (
            100 * (top_customers_full.index + 1) / len(top_customers_full)
        )
        fig = scatter_chart(
            top_customers_full, "Customer_Rank_Pct", "Cumulative_Pct",
            "Revenue Concentration Curve (Pareto)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "X-axis: cumulative % of customers (ranked by revenue). Y-axis: cumulative % of revenue. "
            "A steep early curve indicates high revenue concentration in a small customer base."
        )
    else:
        st.info("No data for the selected filters.")
