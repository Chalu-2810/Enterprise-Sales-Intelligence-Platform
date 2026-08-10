"""
Tests for utils/database.py. All tests use the synthetic_engine /
patched_engine / seeded_engine fixtures from conftest.py -- a temp SQLite
file per test, never the real database/sales_intelligence.db.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

import utils.database as db_module
from utils.database import DatabaseManager, build_where_clause, get_user_row


# --- Schema initialization ---------------------------------------------------

def test_view_and_users_table_are_created(synthetic_engine):
    inspector = inspect(synthetic_engine)
    tables = set(inspector.get_table_names())
    views = set(inspector.get_view_names())
    assert "app_users" in tables
    assert "vw_app_sales" in views


def test_view_exposes_expected_columns(synthetic_engine):
    with synthetic_engine.connect() as conn:
        df_columns = conn.execute(text("SELECT * FROM vw_app_sales LIMIT 1")).keys()
    expected = {"Order_ID", "Region", "Product", "Customer", "Net_Revenue", "Profit_Amount"}
    assert expected.issubset(set(df_columns))


# --- Demo user seeding -------------------------------------------------------

def test_seeding_creates_all_demo_accounts(patched_engine):
    db_module._seed_demo_users_if_empty(patched_engine)
    with patched_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()
    assert count == 3  # admin, analyst, viewer


def test_seeding_is_idempotent(patched_engine):
    db_module._seed_demo_users_if_empty(patched_engine)
    db_module._seed_demo_users_if_empty(patched_engine)  # second call: no-op
    with patched_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()
    assert count == 3


def test_seeded_passwords_are_hashed_not_plaintext(seeded_engine):
    row = get_user_row("admin")
    assert row["password_hash"] != "admin123"
    assert row["password_hash"].startswith("$2")  # bcrypt hash prefix


# --- CRUD helpers -------------------------------------------------------------

def test_get_user_row_is_case_insensitive(seeded_engine):
    assert get_user_row("ADMIN") is not None
    assert get_user_row("Admin")["username"] == "admin"


def test_get_user_row_returns_none_for_unknown_user(seeded_engine):
    assert get_user_row("does-not-exist") is None


def test_record_login_failure_increments_and_locks(seeded_engine):
    from utils.database import record_login_failure, record_login_success

    record_login_failure("viewer", max_attempts=3, lockout_minutes=10)
    record_login_failure("viewer", max_attempts=3, lockout_minutes=10)
    assert get_user_row("viewer")["failed_attempts"] == 2
    assert get_user_row("viewer")["locked_until"] is None

    record_login_failure("viewer", max_attempts=3, lockout_minutes=10)
    assert get_user_row("viewer")["failed_attempts"] == 3
    assert get_user_row("viewer")["locked_until"] is not None

    record_login_success("viewer")
    row = get_user_row("viewer")
    assert row["failed_attempts"] == 0
    assert row["locked_until"] is None


def test_record_login_failure_is_noop_for_unknown_user(seeded_engine):
    from utils.database import record_login_failure
    # Should not raise, and should not create a row.
    record_login_failure("ghost", max_attempts=3, lockout_minutes=10)
    assert get_user_row("ghost") is None


# --- Query builder (build_where_clause) --------------------------------------

def test_build_where_clause_with_no_filters_returns_empty():
    where_sql, params = build_where_clause(None)
    assert where_sql == ""
    assert params == {}

    where_sql, params = build_where_clause({})
    assert where_sql == ""
    assert params == {}


def test_build_where_clause_ignores_all_and_empty_values():
    where_sql, params = build_where_clause({"Region": "All", "Category": "", "Year": []})
    assert where_sql == ""
    assert params == {}


def test_build_where_clause_single_value():
    where_sql, params = build_where_clause({"Region": "North"})
    assert where_sql == ' AND "Region" = :Region'
    assert params == {"Region": "North"}


def test_build_where_clause_list_value_generates_in_clause():
    where_sql, params = build_where_clause({"Region": ["North", "South"]})
    assert "IN (" in where_sql
    assert set(params.values()) == {"North", "South"}


def test_build_where_clause_combines_multiple_filters():
    where_sql, params = build_where_clause({"Region": "North", "Year": 2024})
    # Exact-string assertion (not just substring-in) so a mutation that
    # joined multiple filters with OR instead of AND -- which would still
    # contain both substrings -- is actually caught.
    assert where_sql == ' AND "Region" = :Region AND "Year" = :Year', (
        f"unexpected WHERE clause structure: {where_sql!r}"
    )
    assert params == {"Region": "North", "Year": 2024}


def test_build_where_clause_unknown_filter_key_is_ignored():
    where_sql, params = build_where_clause({"Not_A_Real_Filter": "value"})
    assert where_sql == ""
    assert params == {}


# --- Postgres-portability regression (Task 3 rewrite) ------------------------

def test_get_customer_features_recency_and_tenure_match_expected_values(patched_engine):
    """Locks in the exact arithmetic the pandas rewrite must produce.

    Using the synthetic fixture data (see conftest.py):
      Alice: orders on 2024-01-05 and 2024-03-15 -> Tenure = 70 days
      Bob:   orders on 2024-02-10 and 2024-03-01  -> Tenure = 20 days
      Dataset max order date = 2024-03-15 (Alice's last order)
      -> Alice Recency = 0 days, Bob Recency = 14 days
    """
    db = DatabaseManager()
    features = db.get_customer_features()

    assert {"Recency_Days", "Tenure_Days", "Frequency", "Monetary", "Customer_Key"}.issubset(
        set(features.columns)
    )
    assert "First_Order_Date" not in features.columns  # helper column must be dropped
    assert "Last_Order_Date" not in features.columns

    by_customer = features.set_index("Customer")
    assert by_customer.loc["Alice", "Recency_Days"] == 0.0
    assert by_customer.loc["Alice", "Tenure_Days"] == 70.0
    assert by_customer.loc["Bob", "Recency_Days"] == 14.0
    assert by_customer.loc["Bob", "Tenure_Days"] == 20.0


def test_get_customer_features_handles_empty_result(patched_engine):
    with patched_engine.begin() as conn:
        conn.execute(text("DELETE FROM fact_sales"))

    db = DatabaseManager()
    features = db.get_customer_features()

    assert features.empty
    assert "Recency_Days" in features.columns
    assert "Tenure_Days" in features.columns
