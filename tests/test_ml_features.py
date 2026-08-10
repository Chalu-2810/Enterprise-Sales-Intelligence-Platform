"""
ML regression tests. Two categories:

1. Feature generation contract (get_customer_features) -- uses the DB
   fixtures, same as test_database.py.
2. Pipeline execution smoke tests (CustomerSegmenter, ChurnPredictor) --
   these classes are pure pandas/sklearn with no Streamlit or DB
   dependency, so we hand-build small synthetic DataFrames directly in
   memory. No database involved at all for this half of the file.

Per instructions: we assert the pipelines *run* and produce the expected
*shape*/columns, not that any accuracy/metric crosses a threshold --
accuracy assertions on this little synthetic data would be meaningless
and brittle.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.churn import ChurnPredictor
from models.segmentation import CustomerSegmenter
from utils.database import DatabaseManager

REQUIRED_CUSTOMER_FEATURES = {
    "Customer_Key", "Customer", "Segment", "Frequency", "Monetary",
    "Total_Profit", "Customer_Rating", "Recency_Days", "Tenure_Days",
}


# --- Feature generation contract --------------------------------------------

def test_customer_features_has_all_required_columns(patched_engine):
    db = DatabaseManager()
    features = db.get_customer_features()
    assert REQUIRED_CUSTOMER_FEATURES.issubset(set(features.columns))


def test_customer_features_has_no_missing_recency_or_monetary(patched_engine):
    db = DatabaseManager()
    features = db.get_customer_features()
    assert features["Recency_Days"].isna().sum() == 0, "Recency_Days must be computed for every customer"
    assert features["Monetary"].isna().sum() == 0, "Monetary must be computed for every customer"
    assert features["Frequency"].isna().sum() == 0, "Frequency must be computed for every customer"


# --- Segmentation pipeline smoke test ---------------------------------------

@pytest.fixture
def synthetic_customer_features() -> pd.DataFrame:
    """8 customers with clearly separated RFM profiles -- enough rows for
    KMeans(n_clusters=2) to run without degenerate-cluster warnings."""
    rng = np.random.default_rng(42)
    n = 8
    return pd.DataFrame({
        "Customer_Key": range(1, n + 1),
        "Customer": [f"Cust_{i}" for i in range(1, n + 1)],
        "Segment": ["Enterprise"] * n,
        "Recency_Days": list(rng.integers(0, 10, size=4)) + list(rng.integers(200, 400, size=4)),
        "Frequency": list(rng.integers(20, 40, size=4)) + list(rng.integers(1, 3, size=4)),
        "Monetary": list(rng.integers(5000, 10000, size=4)) + list(rng.integers(50, 500, size=4)),
    })


def test_segmentation_pipeline_executes(synthetic_customer_features):
    segmenter = CustomerSegmenter(n_clusters=2)
    result = segmenter.fit_predict(synthetic_customer_features)

    assert "Cluster" in result.columns
    assert "RFM_Segment" in result.columns
    assert result["RFM_Segment"].isna().sum() == 0, "every customer must receive a segment label"
    assert len(result) == len(synthetic_customer_features)
    assert set(result["RFM_Segment"].unique()).issubset(
        {"Champions", "Loyal Customers", "At Risk", "Lost / Dormant"}
    )


def test_segmentation_ranks_labels_by_actual_rfm_quality(synthetic_customer_features):
    """The fixture's first 4 rows are deliberately high-value (low recency,
    high frequency/monetary) and the last 4 are deliberately low-value.
    This locks in that the BEST customers get the BEST label and the WORST
    customers get the WORST label -- not just that labels come from the
    valid set (which a reversed rank->label mapping would still satisfy)."""
    segmenter = CustomerSegmenter(n_clusters=2)
    result = segmenter.fit_predict(synthetic_customer_features)

    high_value_labels = set(result.iloc[:4]["RFM_Segment"])
    low_value_labels = set(result.iloc[4:]["RFM_Segment"])

    assert high_value_labels == {"Champions"}, (
        f"expected the high-RFM customers labeled 'Champions', got {high_value_labels}"
    )
    assert low_value_labels == {"Loyal Customers"}, (
        f"expected the low-RFM customers labeled the worse of the 2 clusters, got {low_value_labels}"
    )


def test_segment_profile_runs_after_fit_predict(synthetic_customer_features):
    segmenter = CustomerSegmenter(n_clusters=2)
    segmented = segmenter.fit_predict(synthetic_customer_features)
    profile = segmenter.segment_profile(segmented)

    assert "Customers" in profile.columns
    assert profile["Customers"].sum() == len(synthetic_customer_features)


# --- Churn pipeline smoke test ----------------------------------------------

@pytest.fixture
def synthetic_raw_sales() -> pd.DataFrame:
    """20 customers, split into two clearly different pre-cutoff behavior
    profiles so the model has an actual signal to learn (not just labels):

    - Customers 1-10: a single low-value order in Jan 2023, nothing after
      -> low Frequency/Monetary/Tenure pre-cutoff, no post-cutoff activity
      -> labeled Churned.
    - Customers 11-20: three higher-value orders across Jan-Mar 2023, plus
      one more order in June 2024 (after the 180-day cutoff, computed from
      the dataset's max date) -> higher Frequency/Monetary/Tenure
      pre-cutoff, and present after the cutoff -> labeled Not Churned.
    """
    rows = []
    for cust in range(1, 21):
        if cust <= 10:
            rows.append({
                "Customer_Key": cust, "Order_ID": cust * 10 + 1,
                "Order_Date": "2023-01-01", "Net_Revenue": 80.0, "Customer_Rating": 3.0,
            })
        else:
            for i, month in enumerate(["2023-01-01", "2023-02-01", "2023-03-01"]):
                rows.append({
                    "Customer_Key": cust, "Order_ID": cust * 10 + i + 1,
                    "Order_Date": month, "Net_Revenue": 150.0, "Customer_Rating": 4.5,
                })
            rows.append({  # post-cutoff activity -> keeps this customer "active"
                "Customer_Key": cust, "Order_ID": cust * 10 + 9,
                "Order_Date": "2024-06-01", "Net_Revenue": 90.0, "Customer_Rating": 4.5,
            })
    return pd.DataFrame(rows)


def test_churn_build_labeled_dataset_produces_both_classes(synthetic_raw_sales):
    labeled = ChurnPredictor.build_labeled_dataset(synthetic_raw_sales)
    assert set(labeled["Churned"].unique()) == {0, 1}
    assert "Tenure_Days" in labeled.columns
    assert "Avg_Order_Value" in labeled.columns


def test_churn_pipeline_fits_and_predicts_without_error(synthetic_raw_sales):
    labeled = ChurnPredictor.build_labeled_dataset(synthetic_raw_sales)
    predictor = ChurnPredictor().fit(labeled)

    risk = predictor.predict_risk(labeled)
    assert "Churn_Probability" in risk.columns
    assert "Risk_Tier" in risk.columns
    assert risk["Churn_Probability"].between(0, 1).all()
    assert set(risk["Risk_Tier"].dropna().unique()).issubset(
        {"Low Risk", "Medium Risk", "High Risk"}
    )
    # Guards against a degenerate model that predicts the same probability
    # for everyone (would indicate the features carry no real signal --
    # this caught a real bug in an earlier version of this fixture).
    assert risk["Churn_Probability"].nunique() > 1, (
        "model predicted an identical probability for every customer -- "
        "features likely carry no distinguishing signal"
    )

    importances = predictor.feature_importance()
    assert importances["Importance"].sum() == pytest.approx(1.0, abs=0.05)
    assert importances["Importance"].max() > 0  # model must have learned something


def test_churn_predict_risk_before_fit_raises_clear_error(synthetic_raw_sales):
    labeled = ChurnPredictor.build_labeled_dataset(synthetic_raw_sales)
    predictor = ChurnPredictor()
    with pytest.raises(RuntimeError):
        predictor.predict_risk(labeled)
