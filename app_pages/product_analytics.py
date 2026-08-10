"""Product Analytics -- ABC analysis, top/worst products, category scorecard."""
from __future__ import annotations

import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_inr, format_number, format_pct
from utils.filters import render_filter_panel
from charts.plotly_charts import bar_chart, pie_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("📦 Product Analytics")
st.caption("Product-level revenue, margin, and ABC/Pareto classification.")

db = DatabaseManager()
filters = render_filter_panel(db, key_prefix="prod", fields=["Category", "Sub_Category", "Region", "Year"])

kpis = db.get_kpi_summary(filters)
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(kpi_card_html("Active Products", format_number(kpis["total_products"])), unsafe_allow_html=True)
with c2:
    rev_per_prod = kpis["total_revenue"] / kpis["total_products"] if kpis["total_products"] else 0
    st.markdown(kpi_card_html("Revenue / Product", format_inr(rev_per_prod)), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card_html("Overall Margin", format_pct(kpis["profit_margin_pct"])), unsafe_allow_html=True)

tab_top, tab_worst, tab_abc, tab_category = st.tabs(
    ["🏆 Top Products", "📉 Underperformers", "🔠 ABC Analysis", "🗂️ By Category"]
)

with tab_top:
    n = st.slider("Show top N products", 5, 30, 10, key="prod_top_n")
    top_products = db.get_top_products(n, filters)
    if not top_products.empty:
        st.plotly_chart(bar_chart(top_products, "Product", "Net_Revenue", f"Top {n} Products by Revenue"),
                         use_container_width=True)
        st.dataframe(top_products, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")

with tab_worst:
    n_worst = st.slider("Show bottom N products by profit", 5, 30, 10, key="prod_worst_n")
    worst_products = db.get_top_products(n_worst, filters, ascending=True)
    if not worst_products.empty:
        st.plotly_chart(bar_chart(worst_products, "Product", "Profit", f"Bottom {n_worst} Products by Profit"),
                         use_container_width=True)
        st.dataframe(worst_products, use_container_width=True, hide_index=True)
        st.caption("These products may need a pricing review or discontinuation assessment.")
    else:
        st.info("No data for the selected filters.")

with tab_abc:
    abc = db.get_abc_analysis(filters)
    if not abc.empty:
        class_summary = abc.groupby("ABC_Class", observed=True).agg(
            Num_Products=("Product", "count"), Total_Revenue=("Net_Revenue", "sum")
        ).reset_index()
        class_summary["Pct_Of_Revenue"] = (100 * class_summary["Total_Revenue"] / class_summary["Total_Revenue"].sum()).round(1)
        col1, col2 = st.columns([1, 1.3])
        with col1:
            st.plotly_chart(pie_chart(class_summary, "ABC_Class", "Total_Revenue", "Revenue Share by ABC Class"),
                             use_container_width=True)
        with col2:
            st.dataframe(class_summary, use_container_width=True, hide_index=True)
        st.markdown("#### Class A Products (Top Priority)")
        st.dataframe(abc[abc["ABC_Class"] == "A"].head(20), use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")

with tab_category:
    cat_df = db.get_sales_by_dimension("Category", filters)
    if not cat_df.empty:
        cat_df["Margin_Pct"] = (100 * cat_df["Profit"] / cat_df["Net_Revenue"]).round(2)
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(bar_chart(cat_df, "Category", "Net_Revenue", "Revenue by Category"), use_container_width=True)
        with col2:
            st.plotly_chart(bar_chart(cat_df.sort_values("Margin_Pct", ascending=False), "Category", "Margin_Pct",
                                       "Margin % by Category"), use_container_width=True)
        st.dataframe(cat_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data for the selected filters.")
