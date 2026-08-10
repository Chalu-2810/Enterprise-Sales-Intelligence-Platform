"""
Data access layer for the Enterprise Sales Intelligence Platform.

Wraps the pre-built SQLite star-schema database in a single
`DatabaseManager` class so every page queries data the same way. A
comprehensive view (`vw_app_sales`) is created on first run if it does not
already exist, flattening the star schema into one analysis-ready table
that every filter/KPI/chart function queries from.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import DATABASE_PATH, DATABASE_URL
from utils.logger import get_logger

logger = get_logger(__name__)

_CREATE_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS vw_app_sales AS
SELECT
    f.Sales_Key, f.Order_ID, f.Order_Line_ID,
    od.Date AS Order_Date, od.Year AS Year, od.Quarter AS Quarter,
    od.Month AS Month, od.Month_Name AS Month_Name,
    r.Region_Name AS Region, r.Country AS Country, r.State AS State, r.City AS City,
    p.Product_Name AS Product, p.Category AS Category, p.Sub_Category AS Sub_Category,
    p.Unit_Cost AS Unit_Cost, p.Unit_Price AS Unit_Price,
    c.Customer_Name AS Customer, c.Segment AS Segment, c.Customer_Rating AS Customer_Rating,
    c.Customer_Key AS Customer_Key,
    sp.Salesperson_Name AS Salesperson, sp.Salesperson_Key AS Salesperson_Key,
    ch.Channel_Name AS Channel,
    f.Quantity AS Quantity, f.Sales_Amount AS Sales_Amount,
    f.Discount_Amount AS Discount_Amount, f.Cost_Amount AS Cost_Amount,
    f.Profit_Amount AS Profit_Amount, f.Shipping_Cost AS Shipping_Cost,
    (f.Sales_Amount - f.Discount_Amount) AS Net_Revenue,
    f.Payment_Mode AS Payment_Mode, f.Is_Returned AS Is_Returned
FROM fact_sales f
JOIN dim_date od ON f.Order_Date_Key = od.Date_Key
JOIN dim_region r ON f.Region_Key = r.Region_Key
JOIN dim_product p ON f.Product_Key = p.Product_Key
JOIN dim_customer c ON f.Customer_Key = c.Customer_Key
JOIN dim_channel ch ON f.Channel_Key = ch.Channel_Key
LEFT JOIN dim_salesperson sp ON f.Salesperson_Key = sp.Salesperson_Key;
"""

# Application users table -- a separate concern from the sales star schema,
# but kept on the same engine/connection to avoid a second DB config
# surface for what is currently a single-app deployment. Passwords are
# bcrypt hashes; plaintext is never stored. Lockout fields implement basic
# brute-force throttling (see LOGIN_MAX_ATTEMPTS / LOGIN_LOCKOUT_MINUTES).
_CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS app_users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL
);
"""

# Maps the human filter names used across the UI to the underlying view column
_FILTER_COLUMN_MAP: dict[str, str] = {
    "Region": "Region", "Country": "Country", "State": "State", "City": "City",
    "Year": "Year", "Quarter": "Quarter", "Month": "Month",
    "Category": "Category", "Sub_Category": "Sub_Category",
    "Customer": "Customer", "Salesperson": "Salesperson", "Product": "Product",
    "Channel": "Channel", "Segment": "Segment",
}


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    """Create (or reuse) the SQLAlchemy engine and ensure app schema exists.

    Uses ``config.DATABASE_URL``, which defaults to the bundled SQLite file
    but can point at a real server (Postgres, etc.) via the DATABASE_URL
    environment variable for production deployments.
    """
    if DATABASE_URL.startswith("sqlite") and not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DATABASE_PATH}. "
            "Make sure database/sales_intelligence.db is present."
        )
    try:
        # pool_pre_ping issues a lightweight liveness check before handing
        # out a pooled connection, so a stale connection (DB restart, idle
        # timeout, container network blip) fails over transparently
        # instead of surfacing as a confusing query error later.
        engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Could not initialize the database engine for DATABASE_URL scheme "
            f"'{DATABASE_URL.split('://')[0]}': {exc}. If you're pointing at "
            "PostgreSQL, make sure its driver (e.g. psycopg) is in requirements.txt."
        ) from exc
    with engine.begin() as conn:
        conn.execute(text(_CREATE_VIEW_SQL))
        conn.execute(text(_CREATE_USERS_TABLE_SQL))
    _seed_demo_users_if_empty(engine)
    logger.info("Database engine initialized; schema and users verified.")
    return engine


def _seed_demo_users_if_empty(engine: Engine) -> None:
    """Populate app_users from config.DEMO_USERS on first run only.

    This exists purely for zero-config demo/local use. It never overwrites
    existing rows, so once real users are created (or demo passwords are
    changed) via the Settings page, this is a no-op forever after.
    """
    import bcrypt

    from config import DEMO_USERS

    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()
        if count:
            return
        now = datetime.utcnow().isoformat()
        for username, info in DEMO_USERS.items():
            password_hash = bcrypt.hashpw(info["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            conn.execute(
                text(
                    "INSERT INTO app_users "
                    "(username, password_hash, display_name, role, failed_attempts, created_at) "
                    "VALUES (:username, :password_hash, :display_name, :role, 0, :created_at)"
                ),
                {
                    "username": username,
                    "password_hash": password_hash,
                    "display_name": info["name"],
                    "role": info["role"],
                    "created_at": now,
                },
            )
        logger.info("Seeded %d demo user(s) into app_users with hashed passwords.", len(DEMO_USERS))


def get_user_row(username: str) -> Optional[dict[str, Any]]:
    """Fetch one app_users row by username (case-insensitive), or None."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM app_users WHERE lower(username) = lower(:username)"),
            {"username": username},
        ).mappings().first()
        return dict(row) if row else None


def record_login_success(username: str) -> None:
    """Reset failed-attempt counters and stamp last_login_at on success."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE app_users SET failed_attempts = 0, locked_until = NULL, "
                "last_login_at = :now WHERE lower(username) = lower(:username)"
            ),
            {"now": datetime.utcnow().isoformat(), "username": username},
        )


def record_login_failure(username: str, max_attempts: int, lockout_minutes: int) -> None:
    """Increment the failed-attempt counter and lock the account if the
    threshold is reached. No-ops silently if the username doesn't exist,
    so this can't be used to enumerate valid usernames via timing/side effects.
    """
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT failed_attempts FROM app_users WHERE lower(username) = lower(:username)"),
            {"username": username},
        ).first()
        if row is None:
            return
        attempts = row[0] + 1
        locked_until = None
        if attempts >= max_attempts:
            locked_until = (datetime.utcnow() + timedelta(minutes=lockout_minutes)).isoformat()
        conn.execute(
            text(
                "UPDATE app_users SET failed_attempts = :attempts, locked_until = :locked_until "
                "WHERE lower(username) = lower(:username)"
            ),
            {"attempts": attempts, "locked_until": locked_until, "username": username},
        )


def build_where_clause(filters: Optional[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Translate a UI filter dict into a parameterized SQL WHERE clause.

    Args:
        filters: Mapping of filter name -> selected value(s). A value of
            None, "All", or an empty list/tuple is treated as "no filter".

    Returns:
        A tuple of (where_clause_string, bound_params_dict). The clause is
        empty-string safe to append after ``WHERE 1=1``.
    """
    if not filters:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key, value in filters.items():
        column = _FILTER_COLUMN_MAP.get(key)
        if column is None or value in (None, "All", "", []):
            continue
        if isinstance(value, (list, tuple, set)):
            values = [v for v in value if v not in (None, "All", "")]
            if not values:
                continue
            placeholders = []
            for i, v in enumerate(values):
                pname = f"{column}_{i}"
                placeholders.append(f":{pname}")
                params[pname] = v
            clauses.append(f'"{column}" IN ({", ".join(placeholders)})')
        else:
            pname = column
            clauses.append(f'"{column}" = :{pname}')
            params[pname] = value

    where_sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where_sql, params


@st.cache_data(show_spinner=False, ttl=3600)
def run_query(sql: str, params_items: tuple[tuple[str, Any], ...] = ()) -> pd.DataFrame:
    """Execute a parameterized SQL query and return the result as a DataFrame.

    Cached by Streamlit on (sql, params) so repeated page loads with the
    same filters don't re-hit SQLite.

    Args:
        sql: A SQL string with ``:name`` bind parameters.
        params_items: Bind parameters as a hashable tuple of (key, value)
            pairs (dicts aren't hashable, so callers convert before calling).

    Returns:
        Query result as a pandas DataFrame.
    """
    params = dict(params_items)
    engine = get_engine()
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)
    except Exception:
        logger.exception("Query failed: %s | params=%s", sql, params)
        raise


def _params_to_items(params: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(params.items()))


class DatabaseManager:
    """High-level, typed data-access API used by every Streamlit page."""

    def __init__(self) -> None:
        self.engine = get_engine()

    # -- Filter option lists -------------------------------------------------
    def get_filter_options(self) -> dict[str, list[Any]]:
        """Return the distinct values available for every filter dropdown."""
        options: dict[str, list[Any]] = {}
        for label, column in _FILTER_COLUMN_MAP.items():
            df = run_query(f'SELECT DISTINCT "{column}" AS v FROM vw_app_sales WHERE "{column}" IS NOT NULL ORDER BY 1')
            options[label] = df["v"].tolist()
        return options

    # -- KPI summary ----------------------------------------------------------
    def get_kpi_summary(self, filters: Optional[dict[str, Any]] = None) -> dict[str, float]:
        """Return the headline KPI set for the Executive Dashboard."""
        where_sql, params = build_where_clause(filters)
        sql = f"""
            SELECT
                COALESCE(SUM(Net_Revenue), 0) AS total_revenue,
                COALESCE(SUM(Profit_Amount), 0) AS total_profit,
                COALESCE(SUM(Sales_Amount), 0) AS gross_revenue,
                COUNT(DISTINCT Order_ID) AS total_orders,
                COUNT(DISTINCT Customer_Key) AS total_customers,
                COUNT(DISTINCT Product) AS total_products,
                COALESCE(SUM(Is_Returned), 0) AS returned_orders,
                COUNT(*) AS total_line_items
            FROM vw_app_sales WHERE 1=1 {where_sql}
        """
        df = run_query(sql, _params_to_items(params))
        row = df.iloc[0].to_dict()
        row["profit_margin_pct"] = (
            100.0 * row["total_profit"] / row["total_revenue"] if row["total_revenue"] else 0.0
        )
        row["avg_order_value"] = (
            row["total_revenue"] / row["total_orders"] if row["total_orders"] else 0.0
        )
        row["return_rate_pct"] = (
            100.0 * row["returned_orders"] / row["total_line_items"] if row["total_line_items"] else 0.0
        )
        return row

    # -- Grouped sales breakdowns ---------------------------------------------
    def get_sales_by_dimension(self, dimension: str, filters: Optional[dict[str, Any]] = None,
                                metric: str = "Net_Revenue", limit: Optional[int] = None) -> pd.DataFrame:
        """Return revenue/profit aggregated by any dimension column (Region, Category, etc.)."""
        column = _FILTER_COLUMN_MAP.get(dimension, dimension)
        where_sql, params = build_where_clause(filters)
        limit_sql = f"LIMIT {int(limit)}" if limit else ""
        sql = f"""
            SELECT "{column}" AS {column},
                   SUM(Net_Revenue) AS Net_Revenue,
                   SUM(Profit_Amount) AS Profit,
                   COUNT(DISTINCT Order_ID) AS Orders,
                   SUM(Quantity) AS Units
            FROM vw_app_sales WHERE 1=1 {where_sql}
            GROUP BY "{column}"
            ORDER BY {metric} DESC
            {limit_sql}
        """
        return run_query(sql, _params_to_items(params))

    # -- Time trends ----------------------------------------------------------
    def get_trend(self, grain: str = "Month", filters: Optional[dict[str, Any]] = None) -> pd.DataFrame:
        """Return revenue/profit trend at Month, Quarter, or Year grain."""
        where_sql, params = build_where_clause(filters)
        if grain == "Year":
            group_cols, order_cols = "Year", "Year"
        elif grain == "Quarter":
            group_cols, order_cols = "Year, Quarter", "Year, Quarter"
        else:
            group_cols, order_cols = "Year, Month, Month_Name", "Year, Month"
        sql = f"""
            SELECT {group_cols},
                   SUM(Net_Revenue) AS Net_Revenue,
                   SUM(Profit_Amount) AS Profit,
                   COUNT(DISTINCT Order_ID) AS Orders
            FROM vw_app_sales WHERE 1=1 {where_sql}
            GROUP BY {group_cols}
            ORDER BY {order_cols}
        """
        return run_query(sql, _params_to_items(params))

    # -- Top / worst performers -------------------------------------------------
    def get_top_customers(self, n: int = 10, filters: Optional[dict[str, Any]] = None) -> pd.DataFrame:
        where_sql, params = build_where_clause(filters)
        sql = f"""
            SELECT Customer, Segment,
                   SUM(Net_Revenue) AS Net_Revenue,
                   SUM(Profit_Amount) AS Profit,
                   COUNT(DISTINCT Order_ID) AS Orders
            FROM vw_app_sales WHERE 1=1 {where_sql}
            GROUP BY Customer_Key
            ORDER BY Net_Revenue DESC LIMIT {int(n)}
        """
        return run_query(sql, _params_to_items(params))

    def get_top_products(self, n: int = 10, filters: Optional[dict[str, Any]] = None,
                          ascending: bool = False) -> pd.DataFrame:
        where_sql, params = build_where_clause(filters)
        direction = "ASC" if ascending else "DESC"
        sql = f"""
            SELECT Product, Category,
                   SUM(Net_Revenue) AS Net_Revenue,
                   SUM(Profit_Amount) AS Profit,
                   SUM(Quantity) AS Units,
                   100.0*SUM(Profit_Amount)/NULLIF(SUM(Sales_Amount),0) AS Margin_Pct
            FROM vw_app_sales WHERE 1=1 {where_sql}
            GROUP BY Product
            ORDER BY Net_Revenue {direction} LIMIT {int(n)}
        """
        return run_query(sql, _params_to_items(params))

    def get_salesperson_leaderboard(self, filters: Optional[dict[str, Any]] = None) -> pd.DataFrame:
        where_sql, params = build_where_clause(filters)
        sql = f"""
            SELECT Salesperson,
                   SUM(Net_Revenue) AS Net_Revenue,
                   SUM(Profit_Amount) AS Profit,
                   COUNT(DISTINCT Order_ID) AS Deals
            FROM vw_app_sales WHERE Salesperson IS NOT NULL {where_sql}
            GROUP BY Salesperson_Key
            ORDER BY Net_Revenue DESC
        """
        return run_query(sql, _params_to_items(params))

    # -- ABC / Pareto ----------------------------------------------------------
    def get_abc_analysis(self, filters: Optional[dict[str, Any]] = None) -> pd.DataFrame:
        where_sql, params = build_where_clause(filters)
        sql = f"""
            SELECT Product, Category, SUM(Net_Revenue) AS Net_Revenue
            FROM vw_app_sales WHERE 1=1 {where_sql}
            GROUP BY Product
            ORDER BY Net_Revenue DESC
        """
        df = run_query(sql, _params_to_items(params))
        if df.empty:
            return df
        df["Cumulative_Revenue"] = df["Net_Revenue"].cumsum()
        total = df["Net_Revenue"].sum()
        df["Cumulative_Pct"] = 100.0 * df["Cumulative_Revenue"] / total if total else 0.0
        df["ABC_Class"] = pd.cut(
            df["Cumulative_Pct"], bins=[-0.01, 70, 90, 100.01], labels=["A", "B", "C"]
        )
        return df

    # -- Raw fetch for ML modules / NLQ ----------------------------------------
    def get_raw_sales(self, filters: Optional[dict[str, Any]] = None,
                       columns: Optional[list[str]] = None) -> pd.DataFrame:
        where_sql, params = build_where_clause(filters)
        cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
        sql = f'SELECT {cols} FROM vw_app_sales WHERE 1=1 {where_sql}'
        return run_query(sql, _params_to_items(params))

    def get_customer_features(self) -> pd.DataFrame:
        """RFM-style feature table at customer grain, used by ML modules.

        Recency/Tenure are computed in pandas rather than SQL: SQLite's
        ``julianday()`` has no direct PostgreSQL equivalent, and hand-rolling
        per-dialect date arithmetic for one small computation isn't worth
        maintaining two SQL variants. MIN/MAX/COUNT/SUM/AVG below are all
        standard SQL supported identically by both engines.
        """
        sql = """
            SELECT
                Customer_Key, Customer, Segment,
                COUNT(DISTINCT Order_ID) AS Frequency,
                SUM(Net_Revenue) AS Monetary,
                SUM(Profit_Amount) AS Total_Profit,
                MIN(Order_Date) AS First_Order_Date,
                MAX(Order_Date) AS Last_Order_Date,
                AVG(Customer_Rating) AS Customer_Rating
            FROM vw_app_sales
            GROUP BY Customer_Key, Customer, Segment
        """
        df = run_query(sql)
        if df.empty:
            df["Recency_Days"] = pd.Series(dtype="float64")
            df["Tenure_Days"] = pd.Series(dtype="float64")
            return df.drop(columns=["First_Order_Date", "Last_Order_Date"], errors="ignore")

        first_order = pd.to_datetime(df["First_Order_Date"])
        last_order = pd.to_datetime(df["Last_Order_Date"])
        dataset_max_date = last_order.max()  # same reference point the old SQL used
        df["Recency_Days"] = (dataset_max_date - last_order).dt.days.astype(float)
        df["Tenure_Days"] = (last_order - first_order).dt.days.astype(float)
        return df.drop(columns=["First_Order_Date", "Last_Order_Date"])
