"""Machine Learning -- customer segmentation, churn prediction, anomaly detection, recommendations."""
from __future__ import annotations

import streamlit as st

from utils.auth import require_login
from utils.database import DatabaseManager
from utils.theme import inject_css, kpi_card_html
from utils.sidebar import render_sidebar_chrome
from utils.helpers import format_number, format_pct
from models.segmentation import CustomerSegmenter
from models.churn import ChurnPredictor
from models.anomaly import AnomalyDetector
from models.recommendation import ProductRecommender
from charts.plotly_charts import scatter_chart, bar_chart, pie_chart

require_login()
inject_css()

render_sidebar_chrome()

st.title("🤖 Machine Learning Studio")
st.caption("Live models trained on the current database -- not pre-computed stubs.")

db = DatabaseManager()

tab_seg, tab_churn, tab_anomaly, tab_reco = st.tabs(
    ["🧩 Customer Segmentation", "⚠️ Churn Prediction", "🔎 Anomaly Detection", "🛒 Product Recommendations"]
)

# ---------------------------------------------------------------------------
with tab_seg:
    st.markdown("#### K-Means Customer Segmentation (RFM)")
    st.caption("Clusters customers on Recency, Frequency, and Monetary value into business-friendly segments.")
    if st.button("Run Segmentation Model", key="run_seg"):
        with st.spinner("Training K-Means model..."):
            features = db.get_customer_features()
            segmenter = CustomerSegmenter(n_clusters=4)
            segmented = segmenter.fit_predict(features)
            profile = segmenter.segment_profile(segmented)
            st.session_state["segmented_df"] = segmented
            st.session_state["segment_profile"] = profile

    if "segmented_df" in st.session_state:
        profile = st.session_state["segment_profile"]
        segmented = st.session_state["segmented_df"]
        cols = st.columns(4)
        for i, row in profile.iterrows():
            with cols[i % 4]:
                st.markdown(kpi_card_html(row["RFM_Segment"], format_number(row["Customers"]) + " customers"),
                            unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(pie_chart(profile, "RFM_Segment", "Customers", "Customers by Segment"),
                             use_container_width=True)
        with c2:
            st.plotly_chart(
                scatter_chart(segmented, "Recency_Days", "Monetary", "Recency vs Monetary (colored by segment)",
                              color="RFM_Segment", hover_data=["Customer"]),
                use_container_width=True,
            )
        st.dataframe(profile, use_container_width=True, hide_index=True)
        st.dataframe(segmented.sort_values("Monetary", ascending=False).head(20), use_container_width=True, hide_index=True)
    else:
        st.info("Click 'Run Segmentation Model' to train live on the current data.")

# ---------------------------------------------------------------------------
with tab_churn:
    st.markdown("#### Churn Prediction (Random Forest)")
    st.markdown(
        """<div class="insight-band">📌 <b>Methodology:</b> churn is defined using a 180-day
        time-split -- features are computed from orders BEFORE the cutoff, and the label is
        whether the customer ordered AFTER it. This avoids label leakage. Note this measures
        180-day inactivity, not annual attrition -- a genuinely low-frequency customer (2-3
        orders/year) may show as "churned" in a specific 180-day window even though they are a
        normal customer on a longer view.</div>""",
        unsafe_allow_html=True,
    )
    if st.button("Train Churn Model", key="run_churn"):
        with st.spinner("Building leakage-free labels and training Random Forest..."):
            raw = db.get_raw_sales(columns=["Customer_Key", "Order_ID", "Order_Date", "Net_Revenue", "Customer_Rating"])
            labeled = ChurnPredictor.build_labeled_dataset(raw)
            predictor = ChurnPredictor().fit(labeled)
            risk = predictor.predict_risk(labeled)
            st.session_state["churn_risk_df"] = risk
            st.session_state["churn_metrics"] = predictor.metrics
            st.session_state["churn_importance"] = predictor.feature_importance()

    if "churn_risk_df" in st.session_state:
        metrics = st.session_state["churn_metrics"]
        risk = st.session_state["churn_risk_df"]
        importance = st.session_state["churn_importance"]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(kpi_card_html("Model Accuracy", format_pct(metrics.accuracy * 100)), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card_html("Recall (Catches Churners)", format_pct(metrics.recall * 100)), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card_html("ROC-AUC", f"{metrics.roc_auc:.3f}"), unsafe_allow_html=True)
        with c4:
            st.markdown(kpi_card_html("Actual Churn Rate", format_pct(metrics.churn_rate_actual)), unsafe_allow_html=True)

        col1, col2 = st.columns([1, 1.2])
        with col1:
            st.plotly_chart(bar_chart(importance, "Feature", "Importance", "Feature Importance"),
                             use_container_width=True)
        with col2:
            risk_counts = risk["Risk_Tier"].value_counts().reset_index()
            risk_counts.columns = ["Risk_Tier", "Customers"]
            st.plotly_chart(pie_chart(risk_counts, "Risk_Tier", "Customers", "Customers by Risk Tier"),
                             use_container_width=True)

        st.markdown("#### Highest Churn-Risk Customers")
        st.dataframe(
            risk[["Customer_Key", "Frequency", "Monetary", "Tenure_Days", "Churn_Probability", "Risk_Tier"]].head(20),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Click 'Train Churn Model' to run the leakage-free churn classifier live.")

# ---------------------------------------------------------------------------
with tab_anomaly:
    st.markdown("#### Multivariate Anomaly Detection (Isolation Forest)")
    st.caption("Flags unusual combinations of Sales Amount, Discount, Quantity, and Profit jointly -- catches patterns a single-column rule would miss.")
    contamination = st.slider("Expected anomaly rate", 0.01, 0.10, 0.02, step=0.01, key="anomaly_contam")
    if st.button("Run Anomaly Detection", key="run_anomaly"):
        with st.spinner("Scoring transactions..."):
            raw = db.get_raw_sales(columns=["Order_ID", "Product", "Category", "Sales_Amount", "Discount_Amount", "Quantity", "Profit_Amount"])
            detector = AnomalyDetector(contamination=contamination)
            scored = detector.fit_predict(raw)
            st.session_state["anomaly_df"] = scored

    if "anomaly_df" in st.session_state:
        scored = st.session_state["anomaly_df"]
        flagged = scored[scored["Is_Anomaly"]]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(kpi_card_html("Flagged Transactions", format_number(len(flagged))), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card_html("% of All Transactions", format_pct(100 * len(flagged) / len(scored))), unsafe_allow_html=True)
        st.plotly_chart(
            scatter_chart(scored.head(5000), "Sales_Amount", "Discount_Amount", "Sales vs Discount (flagged in red)",
                          color="Is_Anomaly"),
            use_container_width=True,
        )
        st.markdown("#### Most Anomalous Transactions")
        st.dataframe(
            flagged[["Product", "Category", "Sales_Amount", "Discount_Amount", "Quantity", "Profit_Amount", "Anomaly_Score"]].head(25),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Click 'Run Anomaly Detection' to score transactions live.")

# ---------------------------------------------------------------------------
with tab_reco:
    st.markdown("#### Item-Based Product Recommendations")
    st.caption("Built from real order co-occurrence (which products are actually bought together) -- fully explainable, no black box.")
    if "reco_engine" not in st.session_state:
        if st.button("Build Recommendation Engine", key="run_reco"):
            with st.spinner("Building product co-occurrence matrix..."):
                raw = db.get_raw_sales(columns=["Order_ID", "Product", "Sales_Amount"])
                reco = ProductRecommender(n_neighbors=8).fit(raw)
                st.session_state["reco_engine"] = reco
                st.session_state["reco_products"] = reco.top_selling_products(raw, n=50)

    if "reco_engine" in st.session_state:
        reco = st.session_state["reco_engine"]
        products = st.session_state["reco_products"]
        selected_product = st.selectbox("Select a product", products, key="reco_product_select")
        recs = reco.recommend(selected_product, n=5)
        if not recs.empty:
            st.plotly_chart(bar_chart(recs, "Product", "Similarity_Score", f"Frequently Bought With: {selected_product}"),
                             use_container_width=True)
            st.dataframe(recs, use_container_width=True, hide_index=True)
        else:
            st.info("No strong co-purchase signal found for this product.")
        st.caption(
            "Note: similarity scores are naturally modest in this dataset, since products were "
            "sampled independently per order line during data generation rather than from real "
            "basket-affinity behavior -- in production with real transaction baskets, scores would "
            "be considerably stronger."
        )
    else:
        st.info("Click 'Build Recommendation Engine' to fit the model live.")
