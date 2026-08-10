"""
Customer segmentation using K-Means clustering on RFM (Recency, Frequency,
Monetary) features. Clusters are ranked by a composite score and mapped to
business-friendly labels (Champions, Loyal, At Risk, Lost) rather than
exposing raw cluster numbers to the end user.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from config import RANDOM_STATE
from utils.logger import get_logger

logger = get_logger(__name__)

_SEGMENT_LABELS_BY_RANK = ["Champions", "Loyal Customers", "At Risk", "Lost / Dormant"]


class CustomerSegmenter:
    """K-Means-based RFM customer segmentation."""

    def __init__(self, n_clusters: int = 4) -> None:
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.model = KMeans(n_clusters=n_clusters, random_state=RANDOM_STATE, n_init=10)
        self._is_fitted = False

    def fit_predict(self, customer_features: pd.DataFrame) -> pd.DataFrame:
        """Cluster customers and attach a business-friendly segment label.

        Args:
            customer_features: Output of DatabaseManager.get_customer_features(),
                must contain Recency_Days, Frequency, Monetary.

        Returns:
            The input DataFrame with two new columns: Cluster (raw KMeans
            label) and RFM_Segment (business-friendly label).
        """
        df = customer_features.copy()
        rfm = df[["Recency_Days", "Frequency", "Monetary"]].fillna(0)

        # Recency: LOWER is better, so invert before scaling so that higher
        # composite score consistently means "more valuable" across all 3 dims.
        rfm_for_scoring = rfm.copy()
        rfm_for_scoring["Recency_Days"] = -rfm_for_scoring["Recency_Days"]

        X = self.scaler.fit_transform(rfm_for_scoring)
        df["Cluster"] = self.model.fit_predict(X)
        self._is_fitted = True

        # Rank clusters by mean composite (scaled) score, best first
        composite_score = X.mean(axis=1)
        df["_composite_score"] = composite_score
        cluster_rank = (
            df.groupby("Cluster")["_composite_score"].mean().sort_values(ascending=False)
        )
        rank_to_label = {
            cluster: _SEGMENT_LABELS_BY_RANK[i] for i, cluster in enumerate(cluster_rank.index)
        }
        df["RFM_Segment"] = df["Cluster"].map(rank_to_label)
        df.drop(columns=["_composite_score"], inplace=True)

        logger.info("Segmented %d customers into %d clusters.", len(df), self.n_clusters)
        return df

    def segment_profile(self, segmented_df: pd.DataFrame) -> pd.DataFrame:
        """Return a summary table of average RFM values per segment."""
        return (
            segmented_df.groupby("RFM_Segment")
            .agg(
                Customers=("Customer_Key", "count"),
                Avg_Recency_Days=("Recency_Days", "mean"),
                Avg_Frequency=("Frequency", "mean"),
                Avg_Monetary=("Monetary", "mean"),
            )
            .round(1)
            .reset_index()
        )
