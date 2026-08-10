"""
Enterprise Sales Intelligence Platform -- Main Entry Point.

Uses Streamlit's st.navigation/st.Page API so the page list itself is
conditional: while logged out, the ONLY registered page is the login
screen (the sidebar navigation is fully hidden), and the entire
multipage app -- Home plus the 10 analytical pages in pages/ -- only
gets registered once authentication succeeds. This is what makes the
login screen render as a genuine full first screen rather than a page
that merely sits behind a visible sidebar of other pages.

Run with:
    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from config import APP_ICON, APP_TITLE, APP_VERSION, DEMO_USERS
from utils.auth import is_authenticated, login
from utils.database import DatabaseManager
from utils.errors import show_friendly_error
from utils.helpers import format_inr, format_number, format_pct
from utils.logger import get_logger
from utils.sidebar import render_sidebar_chrome
from utils.theme import inject_css, kpi_card_html

logger = get_logger(__name__)

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


def login_page() -> None:
    """Full-screen login view. This is the ONLY page registered while logged out."""
    inject_css()
    left, mid, right = st.columns([1, 1.3, 1])
    with mid:
        st.markdown(
            f"""
            <div class="login-card">
                <div class="login-title">{APP_ICON} {APP_TITLE}</div>
                <div class="login-sub">AI-Powered Sales Analytics &amp; Business Intelligence</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="e.g. admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

        if submitted:
            if login(username, password):
                st.success(f"Welcome, {st.session_state['display_name']}!")
                st.rerun()
            elif lockout_message := st.session_state.pop("_lockout_message", None):
                st.error(f"🔒 {lockout_message}")
            else:
                st.error("Invalid username or password. Try one of the demo accounts below.")

        with st.expander("🔑 Demo credentials"):
            for uname, info in DEMO_USERS.items():
                st.markdown(f"- **{uname}** / `{info['password']}`  — {info['role']}")

        st.caption(f"v{APP_VERSION} · Demo authentication only, see README for details.")


def home_page() -> None:
    """Authenticated Home landing page with a quick-glance overview."""
    inject_css()
    render_sidebar_chrome()

    st.title(f"{APP_ICON} {APP_TITLE}")
    st.caption("AI-Powered Enterprise Sales Intelligence & Business Analytics Platform")

    try:
        db = DatabaseManager()
        kpis = db.get_kpi_summary()
    except Exception:
        show_friendly_error(
            logger,
            "Failed to load KPI summary on Home page.",
            "We couldn't load your dashboard data right now. Please try again shortly, "
            "or contact support if the problem persists.",
        )
        return

    st.markdown("### 📌 At a Glance")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card_html("Net Revenue", format_inr(kpis["total_revenue"]), sentiment="pos"), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card_html("Total Profit", format_inr(kpis["total_profit"]), sentiment="pos"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card_html("Profit Margin", format_pct(kpis["profit_margin_pct"]), sentiment="neutral"), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card_html("Total Orders", format_number(kpis["total_orders"]), sentiment="neutral"), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🧭 Explore the Platform")
    nav_cols = st.columns(3)
    nav_items = [
        ("📊 Executive Dashboard", "Role-based KPI overview with drill-down."),
        ("💰 Sales Analytics", "Revenue, discounts, and channel performance."),
        ("👥 Customer Analytics", "CLV, retention, and RFM segmentation."),
        ("📦 Product Analytics", "ABC/Pareto analysis and product scorecards."),
        ("🌍 Regional Analytics", "Geographic performance and fulfillment."),
        ("🔮 Forecasting", "ML-driven revenue forecasts."),
        ("🤖 Machine Learning", "Segmentation, churn, anomalies, recommendations."),
        ("💬 AI Insights", "Natural-language queries and AI-generated summaries."),
    ]
    if st.session_state.get("role") in ("Business Analyst", "Administrator"):
        nav_items.append(("📄 Reports", "Export to Excel, CSV, and PDF."))
    for i, (name, desc) in enumerate(nav_items):
        with nav_cols[i % 3]:
            st.markdown(
                f"""<div class="kpi-card" style="margin-bottom:14px;">
                <div class="section-title" style="font-size:13.5px;">{name}</div>
                <div class="section-sub">{desc}</div>
                </div>""",
                unsafe_allow_html=True,
            )
    st.info("👈 Use the sidebar to navigate to any module. All data shown is live from the SQLite analytics database.")


# ---------------------------------------------------------------------------
# Conditional navigation: this is the actual fix for "only show login first,
# then show the full dashboard nav after logging in". While logged out, the
# ONLY page in st.navigation is the login page, and position="hidden" removes
# the sidebar nav widget entirely so nothing else is visible or reachable.
# ---------------------------------------------------------------------------
if not is_authenticated():
    pg = st.navigation([st.Page(login_page, title="Login", icon="🔐")], position="hidden")
else:
    # Keep this in sync with the require_role() calls inside reports.py /
    # settings.py -- this only controls whether a link is *shown*; the
    # require_role() guard inside each page is what actually enforces it,
    # so a stale/mismatched list here fails safe (worst case: a visible
    # link that then shows a friendly "access denied" message) rather than
    # unsafe (a hidden but reachable page).
    role = st.session_state.get("role")
    system_pages = []
    if role in ("Business Analyst", "Administrator"):
        system_pages.append(st.Page("app_pages/reports.py", title="Reports", icon="📄"))
    if role == "Administrator":
        system_pages.append(st.Page("app_pages/settings.py", title="Settings", icon="⚙️"))

    nav_sections = {
        "": [st.Page(home_page, title="Home", icon="🏠", default=True)],
        "Analytics": [
            st.Page("app_pages/executive_dashboard.py", title="Executive Dashboard", icon="📊"),
            st.Page("app_pages/sales_analytics.py", title="Sales Analytics", icon="💰"),
            st.Page("app_pages/customer_analytics.py", title="Customer Analytics", icon="👥"),
            st.Page("app_pages/product_analytics.py", title="Product Analytics", icon="📦"),
            st.Page("app_pages/regional_analytics.py", title="Regional Analytics", icon="🌍"),
        ],
        "AI & Forecasting": [
            st.Page("app_pages/forecasting.py", title="Forecasting", icon="🔮"),
            st.Page("app_pages/machine_learning.py", title="Machine Learning", icon="🤖"),
            st.Page("app_pages/ai_insights.py", title="AI Insights", icon="💬"),
        ],
    }
    if system_pages:
        nav_sections["System"] = system_pages

    pg = st.navigation(nav_sections, position="sidebar")

pg.run()
