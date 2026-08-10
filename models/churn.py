"""
Churn prediction model.

Methodology note (read before trusting the output): churn labels are built
using a time-split, not a same-period definition, specifically to avoid
label leakage. A cutoff date is chosen 180 days before the dataset's most
recent order date; every behavioral feature (frequency, monetary value,
tenure) is computed using ONLY orders before that cutoff, and the label is
whether the customer placed ANY order after the cutoff. This mirrors how a
real deployment would work -- predicting future behavior from past behavior
-- rather than a same-window definition that would let the model "see" the
answer inside its own features.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from config import RANDOM_STATE
from utils.logger import get_logger

logger = get_logger(__name__)

CHURN_WINDOW_DAYS = 180
_FEATURES = ["Frequency", "Monetary", "Avg_Order_Value", "Tenure_Days", "Customer_Rating"]


@dataclass
class ChurnModelMetrics:
    accuracy: float
    precision: float
    recall: float
    roc_auc: float
    churn_rate_actual: float


class ChurnPredictor:
    """Random Forest churn classifier with a leakage-free time-split label."""

    def __init__(self) -> None:
        self.model = RandomForestClassifier(
            n_estimators=200, max_depth=6, random_state=RANDOM_STATE, class_weight="balanced"
        )
        self._is_fitted = False
        self.metrics: ChurnModelMetrics | None = None

    @staticmethod
    def build_labeled_dataset(raw_sales: pd.DataFrame) -> pd.DataFrame:
        """Construct the leakage-free feature/label table from raw transactions.

        Args:
            raw_sales: Row-level data with at least Customer_Key, Order_Date,
                Order_ID, Net_Revenue, Customer_Rating.

        Returns:
            One row per customer who had at least one order before the
            cutoff, with behavioral features computed pre-cutoff and a
            binary Churned label computed from post-cutoff activity.
        """
        df = raw_sales.copy()
        df["Order_Date"] = pd.to_datetime(df["Order_Date"])
        max_date = df["Order_Date"].max()
        cutoff = max_date - pd.Timedelta(days=CHURN_WINDOW_DAYS)

        pre = df[df["Order_Date"] <= cutoff]
        post = df[df["Order_Date"] > cutoff]

        active_after_cutoff = set(post["Customer_Key"].unique())

        features = (
            pre.groupby("Customer_Key")
            .agg(
                Frequency=("Order_ID", "nunique"),
                Monetary=("Net_Revenue", "sum"),
                Customer_Rating=("Customer_Rating", "mean"),
                First_Order=("Order_Date", "min"),
                Last_Order=("Order_Date", "max"),
            )
            .reset_index()
        )
        features["Avg_Order_Value"] = features["Monetary"] / features["Frequency"].replace(0, 1)
        features["Tenure_Days"] = (features["Last_Order"] - features["First_Order"]).dt.days
        features["Churned"] = (~features["Customer_Key"].isin(active_after_cutoff)).astype(int)
        return features.drop(columns=["First_Order", "Last_Order"])

    def fit(self, labeled_df: pd.DataFrame) -> "ChurnPredictor":
        """Train the classifier and store held-out evaluation metrics."""
        X = labeled_df[_FEATURES].fillna(0)
        y = labeled_df["Churned"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=RANDOM_STATE, stratify=y
        )
        self.model.fit(X_train, y_train)
        preds = self.model.predict(X_test)
        probs = self.model.predict_proba(X_test)[:, 1]

        self.metrics = ChurnModelMetrics(
            accuracy=accuracy_score(y_test, preds),
            precision=precision_score(y_test, preds, zero_division=0),
            recall=recall_score(y_test, preds, zero_division=0),
            roc_auc=roc_auc_score(y_test, probs) if len(set(y_test)) > 1 else float("nan"),
            churn_rate_actual=100.0 * y.mean(),
        )
        self._is_fitted = True
        logger.info("ChurnPredictor trained. Metrics: %s", self.metrics)
        return self

    def predict_risk(self, labeled_df: pd.DataFrame) -> pd.DataFrame:
        """Score every customer with a churn probability (0-1) for the dashboard."""
        if not self._is_fitted:
            raise RuntimeError("Call .fit() before .predict_risk().")
        X = labeled_df[_FEATURES].fillna(0)
        df = labeled_df.copy()
        df["Churn_Probability"] = self.model.predict_proba(X)[:, 1]
        df["Risk_Tier"] = pd.cut(
            df["Churn_Probability"], bins=[-0.01, 0.33, 0.66, 1.0],
            labels=["Low Risk", "Medium Risk", "High Risk"],
        )
        return df.sort_values("Churn_Probability", ascending=False)

    def feature_importance(self) -> pd.DataFrame:
        """Return feature importances for model-explainability display."""
        if not self._is_fitted:
            raise RuntimeError("Call .fit() before .feature_importance().")
        return pd.DataFrame({
            "Feature": _FEATURES,
            "Importance": self.model.feature_importances_,
        }).sort_values("Importance", ascending=False)
