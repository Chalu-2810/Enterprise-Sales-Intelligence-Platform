"""AI Insights -- rule-based NLG executive summary and natural-language query box."""
from __future__ import annotations

import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css
from utils.sidebar import render_sidebar_chrome
from utils.ai_insights import generate_executive_summary, generate_llm_narrative, is_llm_available
from utils.nlq import NaturalLanguageQueryEngine
from utils.filters import render_filter_panel
from charts.plotly_charts import bar_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("💬 AI Insights")
st.caption("Natural-language business summaries and plain-English data queries.")

llm_status = "🟢 LLM-enhanced narrative active" if is_llm_available() else "🟡 Rule-based NLG (no API key configured, or the optional `openai` package isn't installed)"
st.markdown(f'<div class="insight-band">{llm_status} — see README for how to enable a real LLM narrative.</div>',
            unsafe_allow_html=True)

db = DatabaseManager()

st.markdown("### 🧠 AI-Generated Executive Summary")
filters = render_filter_panel(db, key_prefix="ai", fields=["Region", "Category", "Year"])
facts = generate_executive_summary(db, filters)

if is_llm_available():
    with st.spinner("Generating narrative..."):
        narrative = generate_llm_narrative(facts)
    st.markdown(f'<div class="insight-band">{narrative}</div>', unsafe_allow_html=True)
else:
    for line in facts:
        st.markdown(f'<div class="insight-band">💡 {line}</div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown("### 💬 Ask a Question in Plain English")
st.caption(
    'Try: "Show revenue in the South region for Q2", "Top products by revenue in Electronics", '
    '"What is the return rate for the Online channel?"'
)

nlq_engine = NaturalLanguageQueryEngine(db)
question = st.text_input("Your question", placeholder="e.g. Show revenue in the South region for Q2", key="nlq_input")

if question:
    parsed = nlq_engine.parse(question)
    answer, df = nlq_engine.answer(question)
    st.markdown(f'<div class="insight-band">🤖 {answer}</div>', unsafe_allow_html=True)

    if parsed.recognized_terms:
        st.caption("Recognized: " + ", ".join(parsed.recognized_terms))
    else:
        st.caption("No specific filters recognized — showing overall totals. Try naming a region, category, quarter, or year.")

    if not df.empty and parsed.dimension:
        st.plotly_chart(bar_chart(df.head(10), parsed.dimension, parsed.metric, "Supporting Data"),
                         use_container_width=True)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)

st.markdown(
    """<div class="alert-band">⚠️ <b>How this works:</b> this is a lightweight keyword/regex parser
    that recognizes region, category, channel, segment, quarter, year, and month names in your
    question -- it is not a full LLM. It requires zero API keys and works fully offline. If an
    OpenAI API key is configured (see README), the Executive Summary above can optionally be
    rewritten into more fluent prose by a real LLM call, though the underlying numbers always come
    from the database, never from the model.</div>""",
    unsafe_allow_html=True,
)
