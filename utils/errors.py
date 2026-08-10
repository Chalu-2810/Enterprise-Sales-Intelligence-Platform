"""
Shared Streamlit-safe error handling.

The pattern everywhere in this app is the same: log the full exception
(with traceback) server-side for debugging, and show the user a short,
generic message that never includes exception text, SQL, file paths, or
connection details. This module centralizes that pattern so it's applied
consistently instead of being rewritten slightly differently per page.

Note: `.streamlit/config.toml` also sets `showErrorDetails = false` as an
app-wide safety net for any page that doesn't explicitly catch an
exception -- this helper is for pages that want a friendlier, in-context
message instead of Streamlit's generic full-page error screen.
"""
from __future__ import annotations

import logging

import streamlit as st


def show_friendly_error(logger: logging.Logger, log_message: str, user_message: str) -> None:
    """Log the full exception and render a short, safe message instead.

    Call this from inside an ``except Exception:`` block (so the active
    exception's traceback is captured by ``logger.exception``).

    Args:
        logger: The calling module's logger (from utils.logger.get_logger).
        log_message: Context for the server-side log (no user input needed).
        user_message: Short, safe message shown in the UI. Should never
            include exception text, SQL, file paths, or connection details.
    """
    logger.exception(log_message)
    st.error(user_message)
