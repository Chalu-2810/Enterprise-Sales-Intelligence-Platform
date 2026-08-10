"""Settings -- theme preference, database diagnostics, and about/version info."""
from __future__ import annotations

import streamlit as st

from config import APP_TITLE, APP_VERSION, DATABASE_PATH, DEMO_USERS
from utils.auth import require_role
from utils.database import DatabaseManager
from utils.errors import show_friendly_error
from utils.theme import inject_css
from utils.sidebar import render_sidebar_chrome
from utils.logger import get_logger

logger = get_logger(__name__)

require_role("Administrator")
inject_css()

render_sidebar_chrome()

st.title("⚙️ Settings")

tab_appearance, tab_data, tab_about = st.tabs(["🎨 Appearance", "🗄️ Data Source", "ℹ️ About"])

with tab_appearance:
    st.markdown("### Theme")
    st.write("Use the **Dark Mode** toggle in the sidebar on any page to switch themes instantly.")
    st.caption("Color tokens follow the WCAG-AA-checked two-tier palette documented in the project's UX guidelines.")

with tab_data:
    st.markdown("### Database Connection")
    st.code(str(DATABASE_PATH), language="text")
    try:
        db = DatabaseManager()
        options = db.get_filter_options()
        st.success("✅ Connected successfully.")
        col1, col2, col3 = st.columns(3)
        col1.metric("Regions", len(options.get("Region", [])))
        col2.metric("Products", len(options.get("Product", [])))
        col3.metric("Customers", len(options.get("Customer", [])))
    except Exception:
        show_friendly_error(
            logger,
            "Database connection check failed (Settings diagnostics tab).",
            "❌ Could not connect to the database. Check the server logs for details.",
        )

    st.markdown("### Clear Cache")
    st.caption("Force-refresh cached query results (useful after replacing the database file).")
    if st.button("🔄 Clear Query Cache"):
        st.cache_data.clear()
        st.success("Cache cleared.")

with tab_about:
    st.markdown(f"### {APP_TITLE}")
    st.write(f"**Version:** {APP_VERSION}")
    st.write("**Tech stack:** Streamlit, Python, SQLite, SQLAlchemy, Pandas, NumPy, Plotly, "
             "Altair, scikit-learn, OpenPyXL, fpdf2.")
    st.markdown("#### Demo Accounts")
    for uname, info in DEMO_USERS.items():
        st.write(f"- **{uname}** ({info['role']})")
    st.markdown("#### Security Note")
    st.info(
        "This application uses simple session-based demo authentication for portfolio/demo "
        "purposes. It is not intended for production deployment without a real identity "
        "provider, hashed credential storage, and HTTPS enforcement -- see README."
    )
