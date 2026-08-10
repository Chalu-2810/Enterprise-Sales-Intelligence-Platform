"""
Product recommendation engine.

Uses item-based collaborative filtering built from real order co-occurrence
(which products actually get bought together in the same order) rather than
a black-box similarity model -- fully explainable, and consistent with the
cross-sell affinity analysis from this project's SQL layer (Phase 5).
"""
from __future__ import annotations

import pandas as pd
from sklearn.neighbors import NearestNeighbors
from scipy.sparse import csr_matrix

from utils.logger import get_logger

logger = get_logger(__name__)


class ProductRecommender:
    """Item-based recommender using an order x product co-occurrence matrix."""

    def __init__(self, n_neighbors: int = 6) -> None:
        self.n_neighbors = n_neighbors
        self.model = NearestNeighbors(metric="cosine", algorithm="brute")
        self._is_fitted = False
        self._product_index: dict[str, int] = {}
        self._index_product: dict[int, str] = {}

    def fit(self, raw_sales: pd.DataFrame) -> "ProductRecommender":
        """Build the order-product matrix and fit the nearest-neighbors index.

        Args:
            raw_sales: Row-level data with at least Order_ID and Product columns.
        """
        basket = raw_sales[["Order_ID", "Product"]].drop_duplicates()
        products = sorted(basket["Product"].unique())
        orders = sorted(basket["Order_ID"].unique())
        self._product_index = {p: i for i, p in enumerate(products)}
        self._index_product = {i: p for p, i in self._product_index.items()}
        order_index = {o: i for i, o in enumerate(orders)}

        rows = basket["Product"].map(self._product_index)
        cols = basket["Order_ID"].map(order_index)
        data = [1] * len(basket)
        matrix = csr_matrix((data, (rows, cols)), shape=(len(products), len(orders)))

        n_neighbors = min(self.n_neighbors + 1, len(products))
        self.model = NearestNeighbors(metric="cosine", algorithm="brute", n_neighbors=n_neighbors)
        self.model.fit(matrix)
        self._matrix = matrix
        self._is_fitted = True
        logger.info("ProductRecommender fitted on %d products across %d orders.", len(products), len(orders))
        return self

    def recommend(self, product_name: str, n: int = 5) -> pd.DataFrame:
        """Return the top-N products most frequently co-purchased with the given product.

        Args:
            product_name: The product to find recommendations for.
            n: Number of recommendations to return.

        Returns:
            DataFrame with columns Product, Similarity_Score.
        """
        if not self._is_fitted:
            raise RuntimeError("Call .fit() before .recommend().")
        if product_name not in self._product_index:
            return pd.DataFrame(columns=["Product", "Similarity_Score"])

        idx = self._product_index[product_name]
        distances, indices = self.model.kneighbors(self._matrix[idx], n_neighbors=min(n + 1, self._matrix.shape[0]))
        results = []
        for dist, i in zip(distances[0], indices[0]):
            if i == idx:
                continue
            results.append({"Product": self._index_product[i], "Similarity_Score": round(1 - dist, 3)})
        return pd.DataFrame(results[:n], columns=["Product", "Similarity_Score"])

    def top_selling_products(self, raw_sales: pd.DataFrame, n: int = 20) -> list[str]:
        """Convenience helper: product names to populate a selection dropdown."""
        return (
            raw_sales.groupby("Product")["Sales_Amount"].sum()
            .sort_values(ascending=False).head(n).index.tolist()
        )
