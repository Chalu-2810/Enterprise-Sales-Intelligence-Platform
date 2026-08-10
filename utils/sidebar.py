"""Shared sidebar chrome rendered identically on every authenticated page."""
from __future__ import annotations

import streamlit as st

from utils.auth import current_user_display, logout
from utils.theme import theme_toggle_control


def render_sidebar_chrome(show_logout: bool = True) -> None:
    """Render the user badge, dark-mode toggle, and logout button in the sidebar.

    Call this once near the top of every authenticated page, after
    ``st.set_page_config`` (called once in app.py) and after ``inject_css()``.
    """
    st.sidebar.markdown(f"👤 **{current_user_display()}**")
    theme_toggle_control(st.sidebar)
    if show_logout:
        if st.sidebar.button("🚪 Log Out", use_container_width=True, key="sidebar_logout_btn"):
            logout()
            st.rerun()
    st.sidebar.markdown("---")
