"""
Sales forecasting model.

Uses scikit-learn's LinearRegression over a trend term plus one-hot month
features to capture both the long-run growth trend and month-to-month
seasonality (the Nov-Dec spike / January trough documented in the SQL
analysis phase of this project) -- a lightweight, fully-explainable model
appropriate for a portfolio deployment, not a production forecasting stack.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ForecastResult:
    """Container for forecast output, ready for both charting and PDF export."""
    history: pd.DataFrame          # actual monthly values used for training
    forecast: pd.DataFrame         # future predicted months
    mae: float                     # mean absolute error on in-sample backtest
    mape: float                    # mean absolute percentage error on in-sample backtest


class SalesForecaster:
    """Monthly revenue forecaster: linear trend + month-of-year seasonality."""

    def __init__(self) -> None:
        self.model = LinearRegression()
        self._is_fitted = False
        self._first_period_index = 0

    @staticmethod
    def _build_features(period_index: np.ndarray, month: np.ndarray) -> np.ndarray:
        """One-hot encode month (1-12) and append the linear trend index."""
        month_dummies = np.zeros((len(month), 12))
        for i, m in enumerate(month):
            month_dummies[i, int(m) - 1] = 1.0
        trend = period_index.reshape(-1, 1)
        return np.hstack([trend, month_dummies])

    def fit(self, monthly_df: pd.DataFrame) -> "SalesForecaster":
        """Fit the model on a monthly-grain DataFrame with Year, Month, Net_Revenue.

        Args:
            monthly_df: Must contain columns Year, Month, Net_Revenue, sorted
                chronologically (as returned by DatabaseManager.get_trend("Month")).
        """
        df = monthly_df.sort_values(["Year", "Month"]).reset_index(drop=True)
        self._first_year = int(df["Year"].iloc[0])
        period_index = (df["Year"] - self._first_year) * 12 + df["Month"]
        X = self._build_features(period_index.to_numpy(), df["Month"].to_numpy())
        y = df["Net_Revenue"].to_numpy()
        self.model.fit(X, y)
        self._is_fitted = True
        self._last_period_index = int(period_index.iloc[-1])
        self._history = df
        logger.info("SalesForecaster fitted on %d months of history.", len(df))
        return self

    def backtest(self) -> tuple[float, float]:
        """Return (MAE, MAPE) of in-sample fit as a rough model-quality signal."""
        df = self._history
        period_index = (df["Year"] - self._first_year) * 12 + df["Month"]
        X = self._build_features(period_index.to_numpy(), df["Month"].to_numpy())
        preds = self.model.predict(X)
        mae = mean_absolute_error(df["Net_Revenue"], preds)
        mape = mean_absolute_percentage_error(df["Net_Revenue"], preds) * 100
        return mae, mape

    def predict_next(self, n_months: int = 6) -> ForecastResult:
        """Forecast the next N months beyond the training history.

        Args:
            n_months: How many future months to predict.

        Returns:
            A ForecastResult with history, forecast, and backtest error metrics.
        """
        if not self._is_fitted:
            raise RuntimeError("Call .fit() before .predict_next().")

        future_periods = np.arange(self._last_period_index + 1, self._last_period_index + 1 + n_months)
        future_months = ((future_periods - 1) % 12) + 1
        X_future = self._build_features(future_periods, future_months)
        preds = self.model.predict(X_future)
        preds = np.clip(preds, a_min=0, a_max=None)  # revenue can't be negative

        # NOT `first_year + future_periods // 12` -- that overcounts the
        # year by 1 whenever a forecast month lands on December (i.e.
        # period_index is an exact multiple of 12). Derived from the same
        # definition used in fit(): period_index = (Year-first_year)*12 + Month,
        # so Year = first_year + (period_index - Month) // 12. Verified
        # empirically: the buggy formula mislabeled every December row one
        # year too late (e.g. "Dec 2025" shown for what was actually Dec 2024).
        future_years = self._first_year + (future_periods - future_months) // 12
        forecast_df = pd.DataFrame({
            "Year": future_years.astype(int),
            "Month": future_months.astype(int),
            "Net_Revenue": preds,
            "Type": "Forecast",
        })
        history_df = self._history[["Year", "Month", "Net_Revenue"]].copy()
        history_df["Type"] = "Actual"

        mae, mape = self.backtest()
        return ForecastResult(history=history_df, forecast=forecast_df, mae=mae, mape=mape)
