# Test Suite

## How to run

```bash
pip install -r requirements-dev.txt
pytest
```

Run one file or one test:
```bash
pytest tests/test_auth.py
pytest tests/test_auth.py::test_lockout_triggers_after_max_attempts
```

With a coverage summary (optional -- not a gate, just informational):
```bash
pytest --cov=utils --cov=models --cov-report=term-missing
```

## Expected output

All ~50 tests should pass, in well under 5 seconds (everything runs against
in-memory/temp SQLite files and small in-memory DataFrames -- no network,
no real database, no slow model training). A clean run ends with something
like:

```
tests/test_auth.py .............                                    [ 26%]
tests/test_database.py ....................                         [ 66%]
tests/test_ml_features.py ........                                  [ 82%]
tests/test_metrics.py ...........                                   [ 96%]
tests/test_permissions.py .........                                 [100%]

===================== N passed in 1.2s =====================
```

If a test fails, the failure message includes the expected vs. actual
value directly -- most of these tests assert on hand-calculated numbers
documented in the test's own docstring (see `test_metrics.py` and
`test_database.py::test_get_customer_features_recency_and_tenure_match_expected_values`
in particular), so a failure should be immediately diagnosable without
re-deriving anything.

## What's covered

- **Authentication** (`test_auth.py`): login success/failure, failed-attempt
  counting, lockout after `LOGIN_MAX_ATTEMPTS`, lockout expiry, counter
  reset on success, session timeout, logout, `current_user_display()`.
- **Authorization** (`test_permissions.py`): `require_login()` /
  `require_role()` against the exact role tuples `reports.py`/`settings.py`
  use (Task 2's Viewer/Business Analyst/Administrator matrix).
- **Database** (`test_database.py`): schema/view/table creation, demo-user
  seeding (and its idempotency), password hashing, CRUD helpers,
  `build_where_clause()` (every branch), and a locked-in regression test
  for the Task 3 `get_customer_features()` Postgres-portability rewrite.
- **Business logic / KPIs** (`test_metrics.py`): KPI summary, filtered KPIs,
  grouped breakdowns, trends, top customers/products, ABC/Pareto
  classification -- all against a small synthetic dataset with
  hand-verified expected totals (verified against real SQLite execution
  during development, not just asserted in Python).
- **ML** (`test_ml_features.py`): feature-generation column/completeness
  contract, and execution smoke tests for `CustomerSegmenter` and
  `ChurnPredictor` (including a guard against a degenerate model that
  predicts the same value for everyone -- this caught a real bug in an
  early version of the synthetic churn fixture, where both classes had
  identical pre-cutoff features and the model learned nothing).

## Known limitations

- **Not executed in the environment these tests were written in** --
  that sandbox has no network access to install `streamlit`, `sqlalchemy`,
  `bcrypt`, or `pytest`. The ML pipeline logic (`test_ml_features.py`) and
  the KPI/schema SQL (`test_metrics.py`, `test_database.py`) *were*
  independently verified by running the equivalent logic directly with
  `pandas`/`numpy`/`scikit-learn`/`sqlite3` (all available there) -- but
  **please run the full suite once for real on your machine** before
  relying on it, particularly `test_auth.py` and `test_permissions.py`,
  which depend on `streamlit`/`bcrypt` behavior that couldn't be exercised
  directly.
- **No export functionality tests** (CSV/Excel/PDF generation) -- flagged
  as Low priority in the audit; these are thin wrappers around
  well-tested libraries (openpyxl, fpdf2), so the business-logic risk is
  low. Add if export logic grows more custom formatting/calculation.
- **No UI/page-rendering tests** -- intentionally out of scope per the task
  brief. `require_role()` is tested directly with the same role tuples the
  pages use, which gives equivalent coverage of the authorization logic
  without needing Streamlit's `AppTest` harness.
- **No coverage threshold enforced** -- deliberately, per "don't chase
  100% coverage." `pytest-cov` is included so you can see the number, not
  to gate on it.
- **Streamlit's cache-clearing fixture is global** (`clear_streamlit_caches`
  in `conftest.py`) -- it resets `st.cache_data`/`st.cache_resource` before
  every test to prevent cross-test leakage (see conftest.py's docstring).
  If you add tests that intentionally *want* to test caching behavior
  itself, you'll need to opt out of or adapt that fixture.
