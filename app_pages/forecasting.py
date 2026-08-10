"""Forecasting -- ML-driven revenue forecast using the SalesForecaster model."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_inr, format_pct
from utils.filters import render_filter_panel
from models.forecasting import SalesForecaster
from charts.plotly_charts import line_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("🔮 Sales Forecasting")
st.caption("Linear-trend + seasonal (month) regression forecast, built with scikit-learn.")

db = DatabaseManager()
filters = render_filter_panel(db, key_prefix="forecast", fields=["Region", "Category"])

horizon = st.slider("Forecast horizon (months)", 1, 12, 6)

monthly = db.get_trend("Month", filters)

if len(monthly) < 12:
    st.warning("Not enough monthly history for the selected filters to build a reliable forecast (need at least 12 months).")
else:
    forecaster = SalesForecaster().fit(monthly)
    result = forecaster.predict_next(horizon)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(kpi_card_html("Model MAPE (Backtest)", format_pct(result.mape)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card_html("Model MAE (Backtest)", format_inr(result.mae)), unsafe_allow_html=True)
    with c3:
        next_month_forecast = result.forecast.iloc[0]["Net_Revenue"]
        st.markdown(kpi_card_html("Next Month Forecast", format_inr(next_month_forecast)), unsafe_allow_html=True)

    combined = pd.concat([result.history, result.forecast], ignore_index=True)
    combined["Period"] = combined["Year"].astype(str) + "-" + combined["Month"].astype(str).str.zfill(2)

    import plotly.graph_objects as go
    from config import THEME
    fig = go.Figure()
    actual = combined[combined["Type"] == "Actual"]
    forecast = combined[combined["Type"] == "Forecast"]
    fig.add_trace(go.Scatter(x=actual["Period"], y=actual["Net_Revenue"], name="Actual",
                              mode="lines+markers", line=dict(color=THEME.steel, width=2.5)))
    fig.add_trace(go.Scatter(x=forecast["Period"], y=forecast["Net_Revenue"], name="Forecast",
                              mode="lines+markers", line=dict(color=THEME.coral, width=2.5, dash="dash")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10),
                       legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Forecast Detail")
    st.dataframe(result.forecast.drop(columns=["Type"]), use_container_width=True, hide_index=True)

    st.markdown(
        f"""<div class="alert-band">⚠️ <b>Model limitation:</b> this is an explainable linear-trend +
        month-seasonality regression, not a full ARIMA/Prophet seasonal model. Backtest MAPE is
        {result.mape:.1f}%, which is a reasonable baseline, but a production deployment forecasting
        multiple quarters ahead should use a dedicated time-series model -- see README "Future
        Improvements".</div>""",
        unsafe_allow_html=True,
    )
