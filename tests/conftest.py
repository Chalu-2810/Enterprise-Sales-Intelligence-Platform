"""
Shared test fixtures.

Design choices, spelled out because they're not obvious from the fixture
code alone:

1. We stub `st.session_state`, `st.stop`, `st.error`/`st.warning`/`st.success`
   rather than using Streamlit's AppTest harness. Per the task brief, we're
   testing the underlying functions (utils.auth, utils.database), not
   rendering real pages -- this is faster, more deterministic, and doesn't
   require a running script context.

2. Every test gets a *synthetic* SQLite database built from scratch in a
   pytest tmp_path, using the exact same DDL (`_CREATE_VIEW_SQL`,
   `_CREATE_USERS_TABLE_SQL`) that production uses. This means schema tests
   are validating the real DDL, not a re-implementation of it -- and the
   real database/sales_intelligence.db file is never opened or modified.

3. Streamlit caches (`st.cache_data`, `st.cache_resource`) are cleared
   before every test. `run_query()` is cached by (sql, params) only, not by
   which engine is behind it -- without clearing, two tests using identical
   SQL text against different temp databases could see a stale cached
   result from a previous test. This is a testability gap in the caching
   design, noted for anyone extending these tests, not something changed
   in production code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit as st
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import utils.database as db_module  # noqa: E402


# ---------------------------------------------------------------------------
# Streamlit stubs
# ---------------------------------------------------------------------------
class FakeSessionState(dict):
    """Dict-like stand-in for st.session_state supporting attribute access."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        del self[key]


class PageStopped(Exception):
    """Raised by our st.stop() stub, so tests can assert on it directly
    instead of depending on Streamlit's real script-runner behavior."""


@pytest.fixture(autouse=True)
def fake_session_state(monkeypatch):
    """Replace st.session_state with a plain dict for every test."""
    state = FakeSessionState()
    monkeypatch.setattr(st, "session_state", state, raising=False)
    return state


@pytest.fixture(autouse=True)
def mock_streamlit_ui(monkeypatch):
    """Stub the UI calls auth/permission code makes, recording them instead
    of requiring a real Streamlit script-run context."""
    calls = {"error": [], "warning": [], "success": []}

    def _record(kind):
        def _fn(msg, *a, **kw):
            calls[kind].append(msg)
        return _fn

    monkeypatch.setattr(st, "error", _record("error"), raising=False)
    monkeypatch.setattr(st, "warning", _record("warning"), raising=False)
    monkeypatch.setattr(st, "success", _record("success"), raising=False)

    def _stop():
        raise PageStopped()

    monkeypatch.setattr(st, "stop", _stop, raising=False)
    return calls


@pytest.fixture(autouse=True)
def clear_streamlit_caches():
    """Prevent st.cache_data/st.cache_resource from leaking state between
    tests that use different temp databases (see module docstring, point 3)."""
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


# ---------------------------------------------------------------------------
# Synthetic star-schema database
# ---------------------------------------------------------------------------
# Hand-picked values, chosen so every downstream aggregate can be verified
# by hand in the test assertions (see tests/test_metrics.py for the worked
# arithmetic). Region/Product/Customer grains are deliberately small (2 each)
# to keep expected values easy to check, while still exercising every JOIN
# in _CREATE_VIEW_SQL.
_DIM_DATE = [
    (1, "2024-01-05", 2024, 1, 1, "January"),
    (2, "2024-02-10", 2024, 1, 2, "February"),
    (3, "2024-03-15", 2024, 1, 3, "March"),
    (4, "2024-03-01", 2024, 1, 3, "March"),
]
_DIM_REGION = [
    (1, "North", "India", "TN", "Chennai"),
    (2, "South", "India", "KA", "Bengaluru"),
]
_DIM_PRODUCT = [
    (1, "Widget A", "Widgets", "Standard", 50, 100),
    (2, "Widget B", "Widgets", "Premium", 80, 150),
]
_DIM_CUSTOMER = [
    (1, "Alice", "Enterprise", 4.5),
    (2, "Bob", "SMB", 3.8),
]
_DIM_CHANNEL = [(1, "Online")]
_DIM_SALESPERSON = [(1, "Sam")]

# (Sales_Key, Order_ID, Order_Line_ID, Order_Date_Key, Region_Key, Product_Key,
#  Customer_Key, Channel_Key, Salesperson_Key, Quantity, Sales_Amount,
#  Discount_Amount, Cost_Amount, Profit_Amount, Shipping_Cost, Payment_Mode, Is_Returned)
_FACT_SALES = [
    (1, 1001, 1, 1, 1, 1, 1, 1, 1, 2, 200, 20, 100, 80, 5, "Card", 0),
    (2, 1002, 1, 2, 2, 2, 2, 1, 1, 1, 150, 0, 80, 70, 10, "Cash", 0),
    (3, 1003, 1, 3, 1, 1, 1, 1, 1, 1, 100, 10, 50, 40, 5, "Card", 1),
    (4, 1004, 1, 4, 2, 2, 2, 1, 1, 3, 450, 45, 240, 165, 15, "Card", 0),
]


def _build_synthetic_star_schema(engine) -> None:
    ddl = """
    CREATE TABLE dim_date (Date_Key INTEGER PRIMARY KEY, Date TEXT, Year INTEGER,
        Quarter INTEGER, Month INTEGER, Month_Name TEXT);
    CREATE TABLE dim_region (Region_Key INTEGER PRIMARY KEY, Region_Name TEXT,
        Country TEXT, State TEXT, City TEXT);
    CREATE TABLE dim_product (Product_Key INTEGER PRIMARY KEY, Product_Name TEXT,
        Category TEXT, Sub_Category TEXT, Unit_Cost REAL, Unit_Price REAL);
    CREATE TABLE dim_customer (Customer_Key INTEGER PRIMARY KEY, Customer_Name TEXT,
        Segment TEXT, Customer_Rating REAL);
    CREATE TABLE dim_channel (Channel_Key INTEGER PRIMARY KEY, Channel_Name TEXT);
    CREATE TABLE dim_salesperson (Salesperson_Key INTEGER PRIMARY KEY, Salesperson_Name TEXT);
    CREATE TABLE fact_sales (
        Sales_Key INTEGER PRIMARY KEY, Order_ID INTEGER, Order_Line_ID INTEGER,
        Order_Date_Key INTEGER, Region_Key INTEGER, Product_Key INTEGER,
        Customer_Key INTEGER, Channel_Key INTEGER, Salesperson_Key INTEGER,
        Quantity INTEGER, Sales_Amount REAL, Discount_Amount REAL, Cost_Amount REAL,
        Profit_Amount REAL, Shipping_Cost REAL, Payment_Mode TEXT, Is_Returned INTEGER
    );
    """
    with engine.begin() as conn:
        for stmt in ddl.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        for row in _DIM_DATE:
            conn.execute(text(
                "INSERT INTO dim_date VALUES (:k,:d,:y,:q,:m,:mn)"),
                dict(zip(["k", "d", "y", "q", "m", "mn"], row)))
        for row in _DIM_REGION:
            conn.execute(text(
                "INSERT INTO dim_region VALUES (:k,:n,:c,:s,:city)"),
                dict(zip(["k", "n", "c", "s", "city"], row)))
        for row in _DIM_PRODUCT:
            conn.execute(text(
                "INSERT INTO dim_product VALUES (:k,:n,:cat,:sub,:cost,:price)"),
                dict(zip(["k", "n", "cat", "sub", "cost", "price"], row)))
        for row in _DIM_CUSTOMER:
            conn.execute(text(
                "INSERT INTO dim_customer VALUES (:k,:n,:seg,:rating)"),
                dict(zip(["k", "n", "seg", "rating"], row)))
        for row in _DIM_CHANNEL:
            conn.execute(text("INSERT INTO dim_channel VALUES (:k,:n)"), dict(zip(["k", "n"], row)))
        for row in _DIM_SALESPERSON:
            conn.execute(text("INSERT INTO dim_salesperson VALUES (:k,:n)"), dict(zip(["k", "n"], row)))
        fact_cols = ["sk", "oid", "oli", "dk", "rk", "pk", "ck", "chk", "spk",
                     "qty", "sales", "disc", "cost", "profit", "ship", "pay", "ret"]
        for row in _FACT_SALES:
            conn.execute(text(
                "INSERT INTO fact_sales VALUES "
                "(:sk,:oid,:oli,:dk,:rk,:pk,:ck,:chk,:spk,:qty,:sales,:disc,:cost,:profit,:ship,:pay,:ret)"
            ), dict(zip(fact_cols, row)))


@pytest.fixture
def synthetic_engine(tmp_path):
    """A fresh SQLite engine with the synthetic star schema + the real
    production view/users DDL layered on top, in an isolated temp file.

    Uses as_posix() when building the sqlite URL: a raw Windows Path
    formatted directly into an f-string produces backslashes in the URI
    (e.g. sqlite:///C:\\Users\\...), which SQLAlchemy does not reliably
    parse the same way across versions/platforms. as_posix() normalizes
    to forward slashes everywhere, which is the documented-safe form.

    Explicitly disposes the engine at teardown so the underlying sqlite
    file handle is released before pytest tries to clean up tmp_path --
    without this, Windows in particular can fail to delete a still-open
    file, leaking temp directories across test runs.
    """
    db_path = tmp_path / "test_sales.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    _build_synthetic_star_schema(engine)
    with engine.begin() as conn:
        conn.execute(text(db_module._CREATE_VIEW_SQL))
        conn.execute(text(db_module._CREATE_USERS_TABLE_SQL))
    yield engine
    engine.dispose()


@pytest.fixture
def patched_engine(monkeypatch, synthetic_engine):
    """Point utils.database.get_engine() (and everything that calls it --
    run_query, DatabaseManager, get_user_row, etc.) at the synthetic engine
    instead of the real bundled database, without touching production data."""
    monkeypatch.setattr(db_module, "get_engine", lambda: synthetic_engine)
    return synthetic_engine


@pytest.fixture
def seeded_engine(patched_engine):
    """Same as patched_engine, but with the real demo users seeded in via
    the actual production seeding function (exercises that code path too)."""
    db_module._seed_demo_users_if_empty(patched_engine)
    return patched_engine
