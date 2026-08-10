"""
Configuration module for the Enterprise Sales Intelligence Platform.

Centralizes all constants, paths, theme tokens, and demo credentials so
no other module hardcodes these values. Edit this file to change the
app's behavior without touching page or utility code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent
DATABASE_PATH: Path = BASE_DIR / "database" / "sales_intelligence.db"
REPORTS_DIR: Path = BASE_DIR / "reports"
ASSETS_DIR: Path = BASE_DIR / "assets"
CSS_DIR: Path = ASSETS_DIR / "css"

APP_TITLE: str = "Enterprise Sales Intelligence Platform"
APP_ICON: str = "📊"
APP_VERSION: str = "1.0.0"

# ---------------------------------------------------------------------------
# Database connection. Defaults to the bundled SQLite file for zero-config
# local/demo use. In production, set the DATABASE_URL environment variable
# to a real server (e.g. postgresql+psycopg://user:pass@host:5432/db) --
# SQLite is single-writer and not safe for concurrent multi-user traffic.
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.environ.get("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# ---------------------------------------------------------------------------
# Authentication seed accounts. These are used ONLY to seed the `users`
# table in the database on first run (with bcrypt-hashed passwords) --
# after that, utils/auth.py reads exclusively from the database, never
# from this dict. Override credentials via the Settings page or directly
# in the database once deployed; do not rely on these in production.
# ---------------------------------------------------------------------------
DEMO_USERS: dict[str, dict[str, str]] = {
    "admin": {"password": "admin123", "role": "Administrator", "name": "Alex Morgan"},
    "analyst": {"password": "analyst123", "role": "Business Analyst", "name": "Priya Sharma"},
    "viewer": {"password": "viewer123", "role": "Viewer", "name": "Guest Viewer"},
}

# Session expires after this many minutes of inactivity.
SESSION_TIMEOUT_MINUTES: int = int(os.environ.get("SESSION_TIMEOUT_MINUTES", "60"))

# Failed-login throttling: after this many consecutive failures for a
# username, further attempts are blocked for LOGIN_LOCKOUT_MINUTES.
LOGIN_MAX_ATTEMPTS: int = 5
LOGIN_LOCKOUT_MINUTES: int = 15

# ---------------------------------------------------------------------------
# Optional: AI Insights can be backed by a real LLM if an API key is present.
# Without one, the app automatically falls back to a rule-based natural
# language generator so the app works with zero configuration out of the box.
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")

# ---------------------------------------------------------------------------
# Theme tokens (WCAG-checked palette, carried over from the Power BI design)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ThemeTokens:
    navy: str = "#0B2545"
    steel: str = "#3E7CB1"
    teal: str = "#4C9A8B"
    coral: str = "#D9695F"
    slate: str = "#8A94A6"
    bg_light: str = "#F5F7FA"
    card_light: str = "#FFFFFF"
    text_light: str = "#1B1F27"
    bg_dark: str = "#0F1620"
    card_dark: str = "#1A2333"
    text_dark: str = "#E7ECF3"


THEME = ThemeTokens()

CHART_COLOR_SEQUENCE: list[str] = [
    THEME.steel, THEME.teal, THEME.coral, THEME.slate, "#7A5FB0", "#C9A227",
]

# ---------------------------------------------------------------------------
# Filter definitions used across pages (kept in one place for consistency)
# ---------------------------------------------------------------------------
FILTER_FIELDS: list[str] = [
    "Region", "Country", "State", "Year", "Quarter", "Month",
    "Category", "Sub_Category", "Customer", "Salesperson", "Product",
]

DEFAULT_TOP_N: int = 10
RANDOM_STATE: int = 42
