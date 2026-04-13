import plotly.express as px
import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import apply_filters, build_sidebar_filters, load_context


st.set_page_config(page_title="Training", page_icon="🏃", layout="wide")
st.title("🏃 Training")

ctx = load_context()
with st.sidebar:
    st.header("Global Filters")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="training_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.activities.empty:
    st.info("No training data in selected range.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    mix = (
        fctx.activities.groupby("activity_type", as_index=False)
        .agg(count=("activity_id", "count"))
        .sort_values("count", ascending=False)
    )
    fig_mix = px.pie(mix, names="activity_type", values="count", title="Activity Mix")
    st.plotly_chart(fig_mix, use_container_width=True)

with col2:
    weekly = (
        fctx.activities.set_index("date")
        .resample("W")
        .agg(
            distance_km=("distance_km", "sum"),
            duration_min=("duration_min", "sum"),
            training_stress_score=("training_stress_score", "sum"),
        )
        .reset_index()
    )
    fig_week = px.bar(weekly, x="date", y="distance_km", title="Weekly Distance")
    st.plotly_chart(fig_week, use_container_width=True)

fig_load = px.line(weekly, x="date", y=["training_stress_score", "duration_min"], title="Weekly Load & Duration")
st.plotly_chart(fig_load, use_container_width=True)

metric_cols = [
    "date",
    "activity_type",
    "activity_id",
    "distance_km",
    "duration_min",
    "avg_speed_kmh",
    "avg_hr",
    "avg_power_w",
    "training_stress_score",
    "calories",
    "elevation_gain",
]
visible = [c for c in metric_cols if c in fctx.activities.columns]
st.dataframe(fctx.activities[visible].sort_values("date", ascending=False), use_container_width=True)
