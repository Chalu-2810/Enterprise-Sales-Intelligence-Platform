"""Reusable Plotly chart builders, styled to match the platform's theme."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import CHART_COLOR_SEQUENCE, THEME

_TEMPLATE_LAYOUT = dict(
    font=dict(family="IBM Plex Sans, sans-serif", size=12, color=THEME.text_light),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hoverlabel=dict(bgcolor="white", font_size=12),
)


def _style(fig: go.Figure, title: str | None = None, height: int = 360) -> go.Figure:
    fig.update_layout(**_TEMPLATE_LAYOUT, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=14, color=THEME.navy)))
    return fig


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str = "", orientation: str = "v",
              color: str | None = None, height: int = 360) -> go.Figure:
    """Standard bar chart with the platform's color sequence applied."""
    fig = px.bar(
        df, x=x if orientation == "v" else y, y=y if orientation == "v" else x,
        orientation=orientation, color=color,
        color_discrete_sequence=CHART_COLOR_SEQUENCE,
    )
    fig.update_traces(marker_line_width=0)
    return _style(fig, title, height)


def line_chart(df: pd.DataFrame, x: str, y: str | list[str], title: str = "",
               height: int = 360) -> go.Figure:
    """Line/trend chart, supports single or multiple y series."""
    fig = px.line(df, x=x, y=y, markers=True, color_discrete_sequence=CHART_COLOR_SEQUENCE)
    fig.update_traces(line=dict(width=2.5))
    return _style(fig, title, height)


def dual_axis_line_chart(df: pd.DataFrame, x: str, y1: str, y2: str,
                          y1_name: str, y2_name: str, title: str = "",
                          height: int = 380) -> go.Figure:
    """Dual-axis chart (e.g. Revenue vs Profit trend on separate scales)."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x], y=df[y1], name=y1_name, mode="lines+markers",
                              line=dict(color=THEME.steel, width=2.5)))
    fig.add_trace(go.Scatter(x=df[x], y=df[y2], name=y2_name, mode="lines+markers",
                              line=dict(color=THEME.teal, width=2.5), yaxis="y2"))
    fig.update_layout(
        yaxis=dict(title=y1_name), yaxis2=dict(title=y2_name, overlaying="y", side="right"),
    )
    return _style(fig, title, height)


def pie_chart(df: pd.DataFrame, names: str, values: str, title: str = "",
              height: int = 340, hole: float = 0.45) -> go.Figure:
    """Donut chart for share-of-total breakdowns (channel mix, ABC class, etc.)."""
    fig = px.pie(df, names=names, values=values, hole=hole,
                 color_discrete_sequence=CHART_COLOR_SEQUENCE)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return _style(fig, title, height)


def scatter_chart(df: pd.DataFrame, x: str, y: str, title: str = "", color: str | None = None,
                   size: str | None = None, hover_data: list[str] | None = None,
                   height: int = 380) -> go.Figure:
    """Scatter plot (e.g. discount % vs margin %, or RFM segmentation)."""
    fig = px.scatter(df, x=x, y=y, color=color, size=size, hover_data=hover_data,
                      color_discrete_sequence=CHART_COLOR_SEQUENCE)
    return _style(fig, title, height)


def heatmap_chart(df: pd.DataFrame, x: str, y: str, z: str, title: str = "",
                   height: int = 380) -> go.Figure:
    """Heatmap (e.g. cohort revenue curve)."""
    pivot = df.pivot(index=y, columns=x, values=z)
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index,
        colorscale=[[0, "#FBEAE8"], [0.5, "#F5F7FA"], [1, THEME.teal]],
    ))
    return _style(fig, title, height)


def gauge_chart(value: float, title: str, max_value: float = 100, height: int = 240) -> go.Figure:
    """Gauge chart (e.g. warehouse utilization %, target attainment %)."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": "%"},
        gauge={
            "axis": {"range": [0, max_value]},
            "bar": {"color": THEME.steel},
            "steps": [
                {"range": [0, max_value * 0.5], "color": "#FBEAE8"},
                {"range": [max_value * 0.5, max_value * 0.8], "color": "#FFF3D6"},
                {"range": [max_value * 0.8, max_value], "color": "#E1F0EC"},
            ],
        },
        title={"text": title, "font": {"size": 13}},
    ))
    fig.update_layout(height=height, margin=dict(l=20, r=20, t=40, b=10))
    return fig


def waterfall_chart(labels: list[str], values: list[float], title: str = "",
                     height: int = 380) -> go.Figure:
    """Waterfall chart (e.g. Revenue -> Discount -> Cost -> Shipping -> Profit)."""
    measures = ["relative"] * (len(labels) - 1) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=measures,
        decreasing={"marker": {"color": THEME.coral}},
        increasing={"marker": {"color": THEME.teal}},
        totals={"marker": {"color": THEME.navy}},
    ))
    return _style(fig, title, height)


def choropleth_bubble_map(df: pd.DataFrame, lat_col: str, lon_col: str, size_col: str,
                           color_col: str, text_col: str, title: str = "",
                           height: int = 420) -> go.Figure:
    """Bubble map for regional performance (India-focused)."""
    fig = px.scatter_geo(
        df, lat=lat_col, lon=lon_col, size=size_col, color=color_col,
        text=text_col, color_continuous_scale=[THEME.coral, THEME.slate, THEME.teal],
        scope="asia",
    )
    fig.update_geos(center=dict(lat=22, lon=79), projection_scale=4, showcountries=True)
    return _style(fig, title, height)
