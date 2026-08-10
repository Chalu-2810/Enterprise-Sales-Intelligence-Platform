"""Reports -- export current data views to CSV, Excel, and a branded PDF summary."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from utils.auth import require_role
from utils.database import DatabaseManager
from utils.theme import inject_css
from utils.sidebar import render_sidebar_chrome
from utils.filters import render_filter_panel
from utils.export import to_csv_bytes, to_excel_bytes, build_summary_pdf
from utils.ai_insights import generate_executive_summary

require_role("Business Analyst", "Administrator")
inject_css()

render_sidebar_chrome()

st.title("📄 Reports")
st.caption("Export the current data view to Excel, CSV, or a branded PDF executive summary.")

db = DatabaseManager()
filters = render_filter_panel(db, key_prefix="reports", fields=["Region", "Category", "Year", "Channel"])

timestamp = datetime.now().strftime("%Y%m%d_%H%M")

st.markdown("### 📊 Executive Summary PDF")
if st.button("Generate PDF Report", key="gen_pdf"):
    with st.spinner("Building PDF..."):
        kpis = db.get_kpi_summary(filters)
        top_products = db.get_top_products(10, filters)
        top_regions = db.get_sales_by_dimension("Region", filters)
        insights = generate_executive_summary(db, filters)
        pdf_bytes = build_summary_pdf(kpis, top_products, top_regions, insights)
    st.download_button(
        "⬇️ Download PDF Report", data=pdf_bytes,
        file_name=f"sales_intelligence_summary_{timestamp}.pdf", mime="application/pdf",
    )
    st.success("PDF generated successfully.")

st.markdown("---")
st.markdown("### 📁 Data Exports")

export_options = {
    "Sales by Region": lambda: db.get_sales_by_dimension("Region", filters),
    "Sales by Category": lambda: db.get_sales_by_dimension("Category", filters),
    "Top 20 Customers": lambda: db.get_top_customers(20, filters),
    "Top 20 Products": lambda: db.get_top_products(20, filters),
    "Salesperson Leaderboard": lambda: db.get_salesperson_leaderboard(filters),
    "ABC Analysis": lambda: db.get_abc_analysis(filters),
    "Monthly Trend": lambda: db.get_trend("Month", filters),
}

selected_export = st.selectbox("Choose a dataset to export", list(export_options.keys()))
df = export_options[selected_export]()
st.dataframe(df, use_container_width=True, hide_index=True)

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "⬇️ Download as CSV", data=to_csv_bytes(df),
        file_name=f"{selected_export.replace(' ', '_').lower()}_{timestamp}.csv", mime="text/csv",
    )
with col2:
    st.download_button(
        "⬇️ Download as Excel", data=to_excel_bytes({selected_export: df}),
        file_name=f"{selected_export.replace(' ', '_').lower()}_{timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.markdown("---")
st.markdown("### 📦 Export All Key Views (Multi-Sheet Excel)")
if st.button("Build Full Excel Workbook", key="full_excel"):
    with st.spinner("Assembling workbook..."):
        sheets = {name: fn() for name, fn in export_options.items()}
        workbook_bytes = to_excel_bytes(sheets)
    st.download_button(
        "⬇️ Download Full Workbook", data=workbook_bytes,
        file_name=f"sales_intelligence_full_export_{timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
