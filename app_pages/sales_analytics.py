"""Sales Analytics -- revenue trends, channel mix, discount analysis, salesperson leaderboard."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_inr, format_number, format_pct
from utils.filters import render_filter_panel
from charts.plotly_charts import bar_chart, line_chart, pie_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("💰 Sales Analytics")
st.caption("Revenue drivers, order patterns, channel mix, and salesperson performance.")

db = DatabaseManager()
filters = render_filter_panel(
    db, key_prefix="sales",
    fields=["Region", "Category", "Sub_Category", "Year", "Quarter", "Channel", "Salesperson"],
)

kpis = db.get_kpi_summary(filters)
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(kpi_card_html("Net Revenue", format_inr(kpis["total_revenue"])), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card_html("Total Orders", format_number(kpis["total_orders"])), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card_html("Avg Order Value", format_inr(kpis["avg_order_value"])), unsafe_allow_html=True)
with c4:
    st.markdown(kpi_card_html("Gross Revenue", format_inr(kpis["gross_revenue"])), unsafe_allow_html=True)

tab_trend, tab_channel, tab_discount, tab_leaderboard = st.tabs(
    ["📈 Trends", "🔀 Channel Mix", "🏷️ Discount Analysis", "🏆 Salesperson Leaderboard"]
)

with tab_trend:
    grain = st.radio("Trend granularity", ["Month", "Quarter", "Year"], horizontal=True, key="sales_trend_grain")
    trend = db.get_trend(grain, filters)
    if not trend.empty:
        if grain == "Month":
            trend["Period"] = trend["Year"].astype(str) + "-" + trend["Month"].astype(str).str.zfill(2)
            x_col = "Period"
        elif grain == "Quarter":
            trend["Period"] = trend["Year"].astype(str) + "-" + trend["Quarter"]
            x_col = "Period"
        else:
            x_col = "Year"
        st.plotly_chart(line_chart(trend, x_col, ["Net_Revenue", "Profit"], f"{grain}ly Revenue & Profit"),
                         use_container_width=True)
        st.dataframe(trend, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")

with tab_channel:
    channel_df = db.get_sales_by_dimension("Channel", filters)
    col1, col2 = st.columns(2)
    with col1:
        if not channel_df.empty:
            st.plotly_chart(pie_chart(channel_df, "Channel", "Net_Revenue", "Revenue Share by Channel"),
                             use_container_width=True)
    with col2:
        if not channel_df.empty:
            st.plotly_chart(bar_chart(channel_df, "Channel", "Profit", "Profit by Channel"),
                             use_container_width=True)
    st.dataframe(channel_df, use_container_width=True, hide_index=True)

with tab_discount:
    raw = db.get_raw_sales(filters, columns=["Sales_Amount", "Discount_Amount", "Profit_Amount", "Is_Returned"])
    if not raw.empty:
        raw = raw.copy()
        raw["Discount_Pct"] = (raw["Discount_Amount"] / raw["Sales_Amount"].replace(0, 1)) * 100
        bins = [-0.01, 10, 20, 30, 100]
        labels = ["0-10%", "10-20%", "20-30%", "30%+"]
        raw["Discount_Band"] = pd.cut(raw["Discount_Pct"], bins=bins, labels=labels)
        band_summary = raw.groupby("Discount_Band", observed=True).agg(
            Line_Items=("Sales_Amount", "count"),
            Total_Discount=("Discount_Amount", "sum"),
            Total_Profit=("Profit_Amount", "sum"),
            Return_Rate=("Is_Returned", "mean"),
        ).reset_index()
        band_summary["Profit_Per_Discount_Rupee"] = (
            band_summary["Total_Profit"] / band_summary["Total_Discount"].replace(0, 1)
        ).round(2)
        band_summary["Return_Rate"] = (band_summary["Return_Rate"] * 100).round(2)
        st.plotly_chart(
            bar_chart(band_summary, "Discount_Band", "Profit_Per_Discount_Rupee",
                      "Profit per ₹ Discounted, by Discount Band"),
            use_container_width=True,
        )
        st.dataframe(band_summary, use_container_width=True, hide_index=True)
        st.caption(
            "This reproduces the discount-vs-profitability finding from the SQL analysis phase: "
            "profit-per-rupee-discounted drops sharply once discounts exceed ~10-20%."
        )
    else:
        st.info("No data for the selected filters.")

with tab_leaderboard:
    leaderboard = db.get_salesperson_leaderboard(filters)
    if not leaderboard.empty:
        st.plotly_chart(bar_chart(leaderboard.head(15), "Salesperson", "Net_Revenue", "Top 15 Salespeople by Revenue"),
                         use_container_width=True)
        st.dataframe(leaderboard, use_container_width=True, hide_index=True)
    else:
        st.info("No salesperson data for the selected filters.")
