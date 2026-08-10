"""
Tests for utils/auth.py. Uses the seeded_engine fixture (conftest.py) --
a synthetic, temp SQLite database seeded with the real demo accounts via
the actual production seeding code. The real database/sales_intelligence.db
is never touched.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from config import LOGIN_LOCKOUT_MINUTES, LOGIN_MAX_ATTEMPTS
from utils import auth
from utils.database import get_user_row


def test_login_with_correct_credentials_succeeds(seeded_engine):
    assert auth.login("admin", "admin123") is True
    assert st.session_state["authenticated"] is True
    assert st.session_state["username"] == "admin"
    assert st.session_state["role"] == "Administrator"


def test_login_with_wrong_password_fails(seeded_engine):
    assert auth.login("admin", "wrong-password") is False
    assert "authenticated" not in st.session_state


def test_login_with_unknown_username_fails(seeded_engine):
    assert auth.login("nobody", "whatever") is False
    assert "authenticated" not in st.session_state


def test_failed_attempts_increment_in_database(seeded_engine):
    auth.login("viewer", "wrong-1")
    auth.login("viewer", "wrong-2")
    row = get_user_row("viewer")
    assert row["failed_attempts"] == 2


def test_lockout_triggers_after_max_attempts(seeded_engine):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        auth.login("viewer", "wrong-password")

    row = get_user_row("viewer")
    assert row["locked_until"] is not None

    # Even the *correct* password should now be rejected while locked.
    result = auth.login("viewer", "viewer123")
    assert result is False
    assert "_lockout_message" in st.session_state


def test_lockout_expires_after_window(seeded_engine):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        auth.login("viewer", "wrong-password")

    # Simulate the lockout window having already elapsed.
    engine = seeded_engine
    from sqlalchemy import text
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE app_users SET locked_until = :t WHERE username = 'viewer'"),
            {"t": past},
        )

    assert auth.login("viewer", "viewer123") is True


def test_successful_login_resets_failure_count(seeded_engine):
    auth.login("analyst", "wrong-1")
    auth.login("analyst", "wrong-2")
    assert get_user_row("analyst")["failed_attempts"] == 2

    assert auth.login("analyst", "analyst123") is True
    assert get_user_row("analyst")["failed_attempts"] == 0
    assert get_user_row("analyst")["locked_until"] is None


def test_is_authenticated_false_when_never_logged_in(seeded_engine):
    assert auth.is_authenticated() is False


def test_session_expires_after_inactivity_timeout(seeded_engine):
    auth.login("admin", "admin123")
    assert auth.is_authenticated() is True

    # Backdate last_seen_at beyond SESSION_TIMEOUT_MINUTES.
    st.session_state["last_seen_at"] = datetime.utcnow() - timedelta(hours=2)

    assert auth.is_authenticated() is False
    # Expiry should also clear the session (equivalent to a logout).
    assert "authenticated" not in st.session_state


def test_active_session_extends_last_seen(seeded_engine):
    auth.login("admin", "admin123")
    original = st.session_state["last_seen_at"]
    # A fresh call to is_authenticated() should refresh the timestamp.
    assert auth.is_authenticated() is True
    assert st.session_state["last_seen_at"] >= original


def test_logout_clears_authentication_state(seeded_engine):
    auth.login("admin", "admin123")
    assert auth.is_authenticated() is True

    auth.logout()

    assert auth.is_authenticated() is False
    for key in ("authenticated", "username", "display_name", "role"):
        assert key not in st.session_state


def test_current_user_display_formats_name_and_role(seeded_engine):
    auth.login("admin", "admin123")
    assert auth.current_user_display() == "Alex Morgan (Administrator)"


def test_current_user_display_defaults_when_logged_out():
    assert auth.current_user_display() == "Guest (Viewer)"
