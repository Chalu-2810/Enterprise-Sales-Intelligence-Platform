"""Regional Analytics -- region/country/state/city performance and fulfillment."""
from __future__ import annotations

import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_inr, format_number
from utils.filters import render_filter_panel
from charts.plotly_charts import bar_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("🌍 Regional Analytics")
st.caption("Geographic performance across Region, Country, State, and City.")

db = DatabaseManager()
filters = render_filter_panel(db, key_prefix="region", fields=["Region", "Country", "State", "Year", "Category"])

kpis = db.get_kpi_summary(filters)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(kpi_card_html("Net Revenue", format_inr(kpis["total_revenue"])), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card_html("Total Orders", format_number(kpis["total_orders"])), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card_html("Total Profit", format_inr(kpis["total_profit"])), unsafe_allow_html=True)

tab_region, tab_state, tab_city = st.tabs(["🗺️ By Region", "🏛️ By State", "🏙️ By City"])

with tab_region:
    region_df = db.get_sales_by_dimension("Region", filters)
    if not region_df.empty:
        region_df["Margin_Pct"] = (100 * region_df["Profit"] / region_df["Net_Revenue"]).round(2)
        st.plotly_chart(bar_chart(region_df, "Region", "Net_Revenue", "Revenue by Region"), use_container_width=True)
        st.dataframe(region_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")

with tab_state:
    state_df = db.get_sales_by_dimension("State", filters, limit=15)
    if not state_df.empty:
        st.plotly_chart(bar_chart(state_df, "State", "Net_Revenue", "Top States by Revenue"), use_container_width=True)
        st.dataframe(state_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")

with tab_city:
    city_df = db.get_sales_by_dimension("City", filters, limit=15)
    if not city_df.empty:
        st.plotly_chart(bar_chart(city_df, "City", "Net_Revenue", "Top Cities by Revenue"), use_container_width=True)
        st.dataframe(city_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")
