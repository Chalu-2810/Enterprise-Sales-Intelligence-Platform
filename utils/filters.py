"""Shared sidebar filter panel used across analytical pages."""
from __future__ import annotations

from typing import Any

import streamlit as st

from utils.database import DatabaseManager
from utils.helpers import none_if_all


def render_filter_panel(db: DatabaseManager, key_prefix: str,
                         fields: list[str] | None = None) -> dict[str, Any]:
    """Render the standard filter widgets in the sidebar and return selections.

    Args:
        db: An initialized DatabaseManager used to populate dropdown options.
        key_prefix: Unique prefix so widget keys don't collide across pages.
        fields: Which filters to show (defaults to the most common subset;
            pass the full FILTER_FIELDS list from config for every filter).

    Returns:
        A dict of {filter_name: selected_value_or_None} ready to pass
        straight into any DatabaseManager query method.
    """
    fields = fields or ["Region", "Category", "Sub_Category", "Year", "Quarter", "Channel", "Segment"]
    options = db.get_filter_options()

    st.sidebar.markdown("### 🔍 Filters")
    selections: dict[str, Any] = {}

    for field in fields:
        choices = ["All"] + [str(v) for v in options.get(field, []) if v is not None]
        selected = st.sidebar.selectbox(
            field.replace("_", "-"), choices, key=f"{key_prefix}_{field}_filter"
        )
        selections[field] = none_if_all(selected)

    if st.sidebar.button("↺ Reset Filters", key=f"{key_prefix}_reset"):
        for field in fields:
            st.session_state.pop(f"{key_prefix}_{field}_filter", None)
        st.rerun()

    return selections
