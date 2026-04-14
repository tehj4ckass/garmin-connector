import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import apply_filters, build_sidebar_filters, load_context, inject_custom_css, apply_premium_theme


st.set_page_config(page_title="Correlations", page_icon="🔗", layout="wide")
inject_custom_css()
st.title("🔗 Correlations")

ctx = load_context()
with st.sidebar:
    st.header("Global Filters")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="corr_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.merged_daily.empty:
    st.info("Not enough merged daily data for correlations.")
    st.stop()

data = fctx.merged_daily.copy().sort_values("date")
if "training_stress_score" in data.columns and "avg_hrv" in data.columns:
    data["hrv_next_day"] = data["avg_hrv"].shift(-1)
if "training_stress_score" in data.columns and "sleep_score" in data.columns:
    data["sleep_next_day"] = data["sleep_score"].shift(-1)

col1, col2 = st.columns(2)
with col1:
    if {"training_stress_score", "hrv_next_day"}.issubset(data.columns):
        fig = px.scatter(
            data,
            x="training_stress_score",
            y="hrv_next_day",
            trendline="ols",
            title="TSS (today) vs HRV (next day)",
        )
        fig = apply_premium_theme(fig, graph_type="scatter")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    if {"training_stress_score", "sleep_next_day"}.issubset(data.columns):
        fig = px.scatter(
            data,
            x="training_stress_score",
            y="sleep_next_day",
            trendline="ols",
            title="TSS (today) vs Sleep Score (next day)",
        )
        fig = apply_premium_theme(fig, graph_type="scatter")
        st.plotly_chart(fig, use_container_width=True)

num_cols = [c for c in data.columns if pd.api.types.is_numeric_dtype(data[c])]
if num_cols:
    corr = data[num_cols].corr(numeric_only=True)
    fig_corr = px.imshow(corr, title="Correlation Matrix", text_auto=".2f", aspect="auto")
    fig_corr = apply_premium_theme(fig_corr, graph_type="other")
    st.plotly_chart(fig_corr, use_container_width=True)
