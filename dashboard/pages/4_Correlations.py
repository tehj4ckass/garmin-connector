import pandas as pd
import plotly.express as px
import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import (
    apply_filters,
    build_sidebar_filters,
    load_context,
    inject_custom_css,
    apply_premium_theme,
    render_header,
)

st.set_page_config(page_title="Zusammenhänge", page_icon="🔗", layout="wide")
inject_custom_css()
render_header("🔗 Zusammenhänge", "Wie beeinflussen Training und Erholung einander?")

ctx = load_context()
with st.sidebar:
    st.header("Filter")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="corr_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.merged_daily.empty:
    st.info("Nicht genügend Daten für Korrelationsanalysen.")
    st.stop()

data = fctx.merged_daily.copy().sort_values("date")

# Lag features (today's training → next day's recovery)
if "training_stress_score" in data.columns:
    if "avg_hrv" in data.columns:
        data["hrv_next_day"] = data["avg_hrv"].shift(-1)
    if "sleep_score" in data.columns:
        data["sleep_next_day"] = data["sleep_score"].shift(-1)
    if "recovery_score" in data.columns:
        data["recovery_next_day"] = data["recovery_score"].shift(-1)

# --- Auswirkung von Training auf den Folgetag ---
st.markdown("### Auswirkung von Training auf den Folgetag")
c1, c2, c3 = st.columns(3)

with c1:
    if {"training_stress_score", "hrv_next_day"}.issubset(data.columns):
        d = data.dropna(subset=["training_stress_score", "hrv_next_day"])
        fig = px.scatter(
            d, x="training_stress_score", y="hrv_next_day", trendline="ols",
            title="Belastung → HRV (Folgetag)",
            labels={"training_stress_score": "TSS (heute)", "hrv_next_day": "HRV (morgen)"},
        )
        st.plotly_chart(apply_premium_theme(fig, graph_type="scatter"), use_container_width=True)

with c2:
    if {"training_stress_score", "sleep_next_day"}.issubset(data.columns):
        d = data.dropna(subset=["training_stress_score", "sleep_next_day"])
        fig = px.scatter(
            d, x="training_stress_score", y="sleep_next_day", trendline="ols",
            title="Belastung → Schlaf-Score (Folgetag)",
            labels={"training_stress_score": "TSS (heute)", "sleep_next_day": "Schlaf-Score (morgen)"},
        )
        st.plotly_chart(apply_premium_theme(fig, graph_type="scatter"), use_container_width=True)

with c3:
    if {"training_stress_score", "recovery_next_day"}.issubset(data.columns):
        d = data.dropna(subset=["training_stress_score", "recovery_next_day"])
        fig = px.scatter(
            d, x="training_stress_score", y="recovery_next_day", trendline="ols",
            title="Belastung → Erholung (Folgetag)",
            labels={"training_stress_score": "TSS (heute)", "recovery_next_day": "Erholung (morgen)"},
        )
        st.plotly_chart(apply_premium_theme(fig, graph_type="scatter"), use_container_width=True)

st.divider()

# --- Erholung & Leistung am gleichen Tag ---
st.markdown("### Erholung & Leistung am gleichen Tag")
c1, c2 = st.columns(2)

with c1:
    if {"recovery_score", "training_stress_score"}.issubset(data.columns):
        d = data.dropna(subset=["recovery_score", "training_stress_score"])
        d = d[d["training_stress_score"] > 0]
        if not d.empty:
            fig = px.scatter(
                d, x="recovery_score", y="training_stress_score", trendline="ols",
                title="Erholung → Trainingslast (gleicher Tag)",
                labels={"recovery_score": "Erholung", "training_stress_score": "TSS"},
            )
            st.plotly_chart(apply_premium_theme(fig, graph_type="scatter"), use_container_width=True)

with c2:
    if {"avg_hrv", "training_stress_score"}.issubset(data.columns):
        d = data.dropna(subset=["avg_hrv", "training_stress_score"])
        d = d[d["training_stress_score"] > 0]
        if not d.empty:
            fig = px.scatter(
                d, x="avg_hrv", y="training_stress_score", trendline="ols",
                title="HRV → Trainingslast (gleicher Tag)",
                labels={"avg_hrv": "HRV", "training_stress_score": "TSS"},
            )
            st.plotly_chart(apply_premium_theme(fig, graph_type="scatter"), use_container_width=True)

st.divider()

# --- Korrelationsmatrix (fokussiert auf Schlüsselmetriken) ---
st.markdown("### Korrelationsmatrix")
key_cols = [
    "training_stress_score", "distance_km", "duration_min",
    "recovery_score", "sleep_hours", "sleep_score",
    "avg_hrv", "resting_hr", "avg_stress",
]
avail_cols = [c for c in key_cols if c in data.columns and pd.api.types.is_numeric_dtype(data[c])]
rename_matrix = {
    "training_stress_score": "TSS", "distance_km": "Distanz (km)", "duration_min": "Dauer (min)",
    "recovery_score": "Erholung", "sleep_hours": "Schlaf (h)", "sleep_score": "Schlaf-Score",
    "avg_hrv": "HRV", "resting_hr": "Ruhe-HF", "avg_stress": "Stress",
}
if avail_cols:
    corr = data[avail_cols].rename(columns=rename_matrix).corr(numeric_only=True)
    fig_corr = px.imshow(
        corr,
        title="Korrelationsmatrix",
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale="RdBu",
        zmin=-1, zmax=1,
    )
    fig_corr = apply_premium_theme(fig_corr, graph_type="other")
    st.plotly_chart(fig_corr, use_container_width=True)
    st.caption("+1 = starker positiver Zusammenhang · −1 = starker negativer Zusammenhang · 0 = kein Zusammenhang")
