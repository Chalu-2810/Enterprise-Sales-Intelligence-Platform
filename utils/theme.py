"""
Theme loading and dark/light mode toggle utilities.

Implementation note: the previous version of this module tried to toggle
dark mode by injecting a <script> tag via st.markdown to add a CSS class
to the page body. Streamlit strips <script> execution from st.markdown
for security reasons, so that approach silently did nothing. This version
uses pure CSS instead -- it targets Streamlit's actual DOM via its stable
data-testid attributes (stApp, stSidebar, stHeader, etc.) and swaps a
complete set of CSS custom properties at :root, which always works because
<style> tags (unlike <script>) are not stripped.
"""
from __future__ import annotations

import streamlit as st

from config import CSS_DIR, THEME

_DARK_OVERRIDES = f"""
<style>
:root {{
    --bg: {THEME.bg_dark};
    --card: {THEME.card_dark};
    --text: {THEME.text_dark};
    --border: #2A3547;
}}

/* Streamlit's real containers -- these data-testid selectors are stable
   across Streamlit versions and are what actually needs to go dark. */
.stApp {{
    background-color: {THEME.bg_dark} !important;
}}
[data-testid="stSidebar"] {{
    background-color: #0B1622 !important;
}}
[data-testid="stSidebar"] * {{
    color: #E7ECF3 !important;
}}
[data-testid="stHeader"] {{
    background-color: rgba(0,0,0,0) !important;
}}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
label, .stSelectbox label, .stSlider label, .stRadio label {{
    color: {THEME.text_dark} !important;
}}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{
    color: {THEME.text_dark} !important;
}}
.stDataFrame, .stTable {{
    filter: invert(0.92) hue-rotate(180deg);
}}
input, textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] {{
    background-color: {THEME.card_dark} !important;
    color: {THEME.text_dark} !important;
}}
</style>
"""


def inject_css() -> None:
    """Load the base stylesheet, then layer dark-mode overrides if toggled on."""
    css_path = CSS_DIR / "style.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    if st.session_state.get("dark_mode", False):
        st.markdown(_DARK_OVERRIDES, unsafe_allow_html=True)


def theme_toggle_control(location=None) -> None:
    """Render the dark/light mode toggle switch in the given sidebar container."""
    location = location if location is not None else st.sidebar
    if "dark_mode" not in st.session_state:
        st.session_state["dark_mode"] = False
    dark = location.toggle("🌙 Dark Mode", value=st.session_state["dark_mode"], key="dark_mode_toggle")
    if dark != st.session_state["dark_mode"]:
        st.session_state["dark_mode"] = dark
        st.rerun()


def kpi_card_html(label: str, value: str, delta: str | None = None,
                   sentiment: str = "neutral") -> str:
    """Build the HTML for one KPI card matching the Phase-10 card anatomy.

    Args:
        label: Uppercase KPI name shown at the top of the card.
        value: Pre-formatted display value (e.g. "₹560.4 Cr").
        delta: Optional delta string (e.g. "▲ 3.4% YoY").
        sentiment: One of "pos", "neg", "neutral" -- controls accent color.
    """
    delta_html = f'<div class="kpi-delta {sentiment}">{delta}</div>' if delta else ""
    return f"""
    <div class="kpi-card">
        <div class="accent-bar {sentiment}"></div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """
