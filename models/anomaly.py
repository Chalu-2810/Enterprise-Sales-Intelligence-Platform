"""
Anomaly detection on individual order line items.

Uses Isolation Forest across Sales_Amount, Discount_Amount, Quantity, and
Profit_Amount jointly (multivariate), which catches suspicious COMBINATIONS
that a single-column IQR rule (used earlier in this project's Excel
cleaning workflow) would miss -- e.g. a normal sales amount paired with an
abnormally large discount, or a high quantity at an abnormally low
per-unit profit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from config import RANDOM_STATE
from utils.logger import get_logger

logger = get_logger(__name__)

_ANOMALY_FEATURES = ["Sales_Amount", "Discount_Amount", "Quantity", "Profit_Amount"]


class AnomalyDetector:
    """Isolation Forest-based multivariate anomaly detector for transactions."""

    def __init__(self, contamination: float = 0.02) -> None:
        """
        Args:
            contamination: Expected proportion of anomalous rows (Isolation
                Forest uses this to set its decision threshold). 2% is a
                deliberately conservative default so the flagged list stays
                small enough for an analyst to actually review by hand.
        """
        self.model = IsolationForest(
            contamination=contamination, random_state=RANDOM_STATE, n_estimators=200
        )
        self._is_fitted = False

    def fit_predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Score every row and flag the most anomalous transactions.

        Args:
            df: Row-level sales data containing the 4 feature columns.

        Returns:
            Input DataFrame with two new columns: Anomaly_Score (lower =
            more anomalous) and Is_Anomaly (bool).
        """
        data = df[_ANOMALY_FEATURES].fillna(0)
        preds = self.model.fit_predict(data)
        scores = self.model.decision_function(data)
        self._is_fitted = True

        result = df.copy()
        result["Anomaly_Score"] = scores
        result["Is_Anomaly"] = preds == -1
        n_flagged = int(result["Is_Anomaly"].sum())
        logger.info("AnomalyDetector flagged %d of %d rows as anomalous.", n_flagged, len(result))
        return result.sort_values("Anomaly_Score")
