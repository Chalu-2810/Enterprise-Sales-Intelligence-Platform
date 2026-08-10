"""Export utilities: CSV, Excel, and PDF report generation."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pandas as pd
from fpdf import FPDF

from config import APP_TITLE
from utils.helpers import format_number, format_pct


def _format_inr_ascii(value: float, decimals: int = 2) -> str:
    """ASCII-safe rupee formatter for the PDF report.

    The core Helvetica font bundled with fpdf2 only supports Latin-1, which
    does not include the '(Rs symbol)' glyph -- rather than embedding a
    Unicode font just for one symbol, PDF output uses the universally
    understood 'Rs.' prefix while the Streamlit UI itself still shows the
    real currency symbol via utils.helpers.format_inr.
    """
    if value is None:
        return "Rs. 0.00"
    abs_value = abs(value)
    sign = "-" if value < 0 else ""
    if abs_value >= 1_00_00_000:
        return f"{sign}Rs. {abs_value / 1_00_00_000:.{decimals}f} Cr"
    if abs_value >= 1_00_000:
        return f"{sign}Rs. {abs_value / 1_00_000:.{decimals}f} L"
    return f"{sign}Rs. {abs_value:,.{decimals}f}"


def _sanitize_for_pdf(text: str) -> str:
    """Make arbitrary text safe for fpdf2's default core font (Helvetica),
    which only supports Latin-1.

    Two real bugs motivated this: (1) AI-generated insight sentences embed
    the real rupee symbol via utils.helpers.format_inr (unlike the KPI
    table above, which already used the ASCII-safe _format_inr_ascii --
    the insights path was missed), and (2) product/region/customer names
    pulled from the database aren't guaranteed ASCII either. Both raised
    fpdf.errors.FPDFUnicodeEncodingException and crashed PDF export
    entirely, for every user, whenever a revenue figure was non-trivial.

    Strategy: replace the handful of common non-Latin-1 characters likely
    to appear (currency symbol, smart quotes/dashes -- the latter also
    guards the optional LLM-narrative path, which commonly emits these)
    with sensible ASCII equivalents, then fall back to replacing anything
    still left with '?' so this can never crash again, even on characters
    not explicitly mapped below.
    """
    if not text:
        return text
    replacements = {
        "\u20b9": "Rs.",  # rupee sign
        "\u2018": "'", "\u2019": "'",  # curly single quotes
        "\u201c": '"', "\u201d": '"',  # curly double quotes
        "\u2013": "-", "\u2014": "-",  # en dash, em dash
        "\u2026": "...",  # ellipsis
        "\u2022": "-",  # bullet
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to CSV bytes for st.download_button."""
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Serialize one or more DataFrames into a single multi-sheet Excel file.

    Args:
        sheets: Mapping of sheet name -> DataFrame.

    Returns:
        Raw XLSX file bytes.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe_name = name[:31]  # Excel sheet name limit
            df.to_excel(writer, sheet_name=safe_name, index=False)
    return buffer.getvalue()


class _ReportPDF(FPDF):
    """A minimal branded PDF report layout."""

    def header(self) -> None:  # noqa: D102 (FPDF hook, not a normal method)
        self.set_fill_color(11, 37, 69)  # navy
        self.rect(0, 0, 210, 22, style="F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.set_xy(10, 6)
        self.cell(150, 10, APP_TITLE, ln=False)
        self.set_font("Helvetica", "", 9)
        self.set_xy(10, 15)
        self.cell(150, 6, f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')}", ln=False)
        self.set_text_color(0, 0, 0)
        self.ln(20)

    def footer(self) -> None:  # noqa: D102
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(190, 10, f"Page {self.page_no()}", align="C")


def build_summary_pdf(kpis: dict[str, Any], top_products: pd.DataFrame,
                       top_regions: pd.DataFrame, insights: list[str]) -> bytes:
    """Build an executive summary PDF report from KPI and table data.

    Args:
        kpis: Output of DatabaseManager.get_kpi_summary().
        top_products: Top-N products DataFrame (Product, Net_Revenue, Profit...).
        top_regions: Sales-by-region DataFrame (Region, Net_Revenue, Profit...).
        insights: List of plain-text AI-generated insight sentences.

    Returns:
        Raw PDF file bytes.
    """
    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(190, 8, "Executive Summary", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)

    kpi_lines = [
        ("Net Revenue", _format_inr_ascii(kpis.get("total_revenue", 0))),
        ("Total Profit", _format_inr_ascii(kpis.get("total_profit", 0))),
        ("Profit Margin", format_pct(kpis.get("profit_margin_pct", 0))),
        ("Total Orders", format_number(kpis.get("total_orders", 0))),
        ("Total Customers", format_number(kpis.get("total_customers", 0))),
        ("Avg Order Value", _format_inr_ascii(kpis.get("avg_order_value", 0))),
        ("Return Rate", format_pct(kpis.get("return_rate_pct", 0))),
    ]
    col_w = 95
    for i in range(0, len(kpi_lines), 2):
        pair = kpi_lines[i:i + 2]
        for label, value in pair:
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.cell(col_w, 7, f"{label}:", border=0)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.cell(col_w, 7, value, border=0)
        pdf.ln(7)

    pdf.ln(4)
    pdf.set_x(10)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "AI-Generated Insights", ln=True)
    pdf.set_font("Helvetica", "", 9.5)
    for line in insights:
        pdf.set_x(10)
        pdf.multi_cell(190, 6, _sanitize_for_pdf(f"-  {line}"))
    pdf.ln(2)

    def render_table(title: str, df: pd.DataFrame, cols: list[str], widths: list[int]) -> None:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(190, 8, title, ln=True)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(245, 247, 250)
        for col, w in zip(cols, widths):
            pdf.cell(w, 7, col, border=1, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for _, row in df.head(10).iterrows():
            for col, w in zip(cols, widths):
                val = row.get(col, "")
                if isinstance(val, float):
                    val = f"{val:,.0f}"
                pdf.cell(w, 6.5, _sanitize_for_pdf(str(val))[:28], border=1)
            pdf.ln()
        pdf.ln(4)

    if not top_regions.empty:
        render_table("Revenue by Region", top_regions, ["Region", "Net_Revenue", "Profit", "Orders"],
                     [50, 45, 45, 40])
    if not top_products.empty:
        render_table("Top Products", top_products, ["Product", "Category", "Net_Revenue", "Margin_Pct"],
                     [65, 40, 40, 35])

    return bytes(pdf.output(dest="S"))
