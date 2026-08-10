"""
Tests for utils/auth.py::require_login / require_role.

We test require_role() directly with each role rather than rendering the
actual reports.py/settings.py pages -- those pages call require_role() as
their very first line (verified in Task 2), so testing the helper with the
exact role tuples each page uses gives equivalent coverage without needing
Streamlit's page-execution machinery.
"""
from __future__ import annotations

from datetime import datetime

import pytest
import streamlit as st

from tests.conftest import PageStopped
from utils.auth import require_login, require_role

REPORTS_ROLES = ("Business Analyst", "Administrator")  # matches app_pages/reports.py
SETTINGS_ROLES = ("Administrator",)  # matches app_pages/settings.py


def _log_in_as(role: str) -> None:
    st.session_state["authenticated"] = True
    st.session_state["username"] = role.lower().replace(" ", "")
    st.session_state["display_name"] = "Test User"
    st.session_state["role"] = role
    st.session_state["last_seen_at"] = datetime.utcnow()


def test_require_login_stops_when_not_authenticated():
    with pytest.raises(PageStopped):
        require_login()


def test_require_login_passes_when_authenticated():
    _log_in_as("Viewer")
    require_login()  # should not raise


# --- Viewer -----------------------------------------------------------------

def test_viewer_cannot_access_reports():
    _log_in_as("Viewer")
    with pytest.raises(PageStopped):
        require_role(*REPORTS_ROLES)


def test_viewer_cannot_access_settings():
    _log_in_as("Viewer")
    with pytest.raises(PageStopped):
        require_role(*SETTINGS_ROLES)


# --- Business Analyst --------------------------------------------------------

def test_business_analyst_can_access_reports():
    _log_in_as("Business Analyst")
    require_role(*REPORTS_ROLES)  # should not raise


def test_business_analyst_cannot_access_settings():
    _log_in_as("Business Analyst")
    with pytest.raises(PageStopped):
        require_role(*SETTINGS_ROLES)


# --- Administrator -----------------------------------------------------------

def test_administrator_can_access_reports():
    _log_in_as("Administrator")
    require_role(*REPORTS_ROLES)  # should not raise


def test_administrator_can_access_settings():
    _log_in_as("Administrator")
    require_role(*SETTINGS_ROLES)  # should not raise


def test_require_role_denial_message_names_required_roles(mock_streamlit_ui):
    _log_in_as("Viewer")
    with pytest.raises(PageStopped):
        require_role(*SETTINGS_ROLES)
    assert any("Administrator" in msg for msg in mock_streamlit_ui["error"])


def test_require_role_also_enforces_login():
    """require_role() must reject an unauthenticated session, not just a
    wrong-role one -- it calls require_login() internally."""
    with pytest.raises(PageStopped):
        require_role(*SETTINGS_ROLES)
