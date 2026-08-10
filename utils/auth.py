"""
Session-based authentication for the Enterprise Sales Intelligence Platform.

Credentials are stored in the `app_users` table (bcrypt-hashed passwords,
seeded once from config.DEMO_USERS on first run -- see
utils/database.py::_seed_demo_users_if_empty). Sessions expire after
config.SESSION_TIMEOUT_MINUTES of inactivity, and repeated failed logins
lock the account for config.LOGIN_LOCKOUT_MINUTES (see
config.LOGIN_MAX_ATTEMPTS). This is real, production-appropriate
authentication for a single-app Streamlit deployment -- it does not use
JWTs because there is no separate API/service boundary that needs a
bearer token; the session lives entirely in Streamlit's own
per-connection `session_state`.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import bcrypt
import streamlit as st

from config import LOGIN_LOCKOUT_MINUTES, LOGIN_MAX_ATTEMPTS, SESSION_TIMEOUT_MINUTES
from utils.database import get_user_row, record_login_failure, record_login_success
from utils.logger import get_logger

logger = get_logger(__name__)

_SESSION_KEYS = ("authenticated", "username", "display_name", "role", "login_at", "last_seen_at")


def is_authenticated() -> bool:
    """Return True if the current session has a logged-in, non-expired user."""
    if not st.session_state.get("authenticated", False):
        return False

    last_seen = st.session_state.get("last_seen_at")
    if last_seen is not None:
        idle_for = datetime.utcnow() - last_seen
        if idle_for > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            logger.info("Session for '%s' expired after %s of inactivity.",
                        st.session_state.get("username"), idle_for)
            logout()
            return False

    st.session_state["last_seen_at"] = datetime.utcnow()
    return True


def login(username: str, password: str) -> bool:
    """Attempt to authenticate a user against the app_users table.

    Args:
        username: The username entered on the login form.
        password: The password entered on the login form.

    Returns:
        True if credentials matched, the account isn't locked, and the
        session was authenticated.
    """
    username = username.strip().lower()
    user = get_user_row(username)

    if user is None:
        # Don't reveal whether the username exists; use the same
        # generic failure path as a wrong-password attempt.
        logger.warning("Failed login attempt for unknown username '%s'.", username)
        return False

    locked_until = user.get("locked_until")
    if locked_until and datetime.fromisoformat(locked_until) > datetime.utcnow():
        logger.warning("Login blocked for locked-out account '%s'.", username)
        st.session_state["_lockout_message"] = (
            f"Account temporarily locked due to repeated failed attempts. "
            f"Try again after {datetime.fromisoformat(locked_until).strftime('%H:%M UTC')}."
        )
        return False

    if bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        record_login_success(username)
        now = datetime.utcnow()
        st.session_state["authenticated"] = True
        st.session_state["username"] = username
        st.session_state["display_name"] = user["display_name"]
        st.session_state["role"] = user["role"]
        st.session_state["login_at"] = now
        st.session_state["last_seen_at"] = now
        st.session_state.pop("_lockout_message", None)
        logger.info("User '%s' logged in successfully.", username)
        return True

    record_login_failure(username, LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_MINUTES)
    logger.warning("Failed login attempt for username '%s'.", username)
    return False


def logout() -> None:
    """Clear all authentication-related session state."""
    for key in _SESSION_KEYS:
        st.session_state.pop(key, None)


def require_login() -> None:
    """Guard clause for every protected page.

    Call this as the first line of every page in ``app_pages/``. If the
    user is not authenticated (or the session has expired), it renders a
    message and stops page execution.
    """
    if not is_authenticated():
        st.warning("🔒 Please log in from the **Home** page to access this section.")
        st.stop()


def require_role(*allowed_roles: str) -> None:
    """Guard clause for role-restricted pages (e.g. Settings).

    Call after require_login(). Stops execution with a clear message if
    the current user's role isn't in allowed_roles.
    """
    require_login()
    role = st.session_state.get("role")
    if role not in allowed_roles:
        st.error(f"⛔ This section requires one of these roles: {', '.join(allowed_roles)}. "
                  f"Your current role is **{role}**.")
        st.stop()


def current_user_display() -> str:
    """Return a friendly 'Name (Role)' string for the sidebar."""
    name = st.session_state.get("display_name", "Guest")
    role = st.session_state.get("role", "Viewer")
    return f"{name} ({role})"
