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
    calculate_weekly_trend,
    render_header
)


render_header("🏃 Training", "Analyse deiner sportlichen Aktivitäten.")

ctx = load_context()
with st.sidebar:
    st.header("Filter")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="training_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.activities.empty:
    st.info("Keine Trainingsdaten im gewählten Zeitraum.")
    st.stop()

# --- Metric Cards with Trends ---
st.markdown("### Aktuelle Trends (vs. Vorwoche)")
col1, col2, col3, col4 = st.columns(4)

act_val, act_delta = calculate_weekly_trend(fctx.activities, "activity_id", agg="count")
dist_val, dist_delta = calculate_weekly_trend(fctx.daily_training, "distance_km", agg="sum")
tss_val, tss_delta = calculate_weekly_trend(fctx.daily_training, "training_stress_score", agg="sum")
dur_val, dur_delta = calculate_weekly_trend(fctx.daily_training, "duration_min", agg="sum")

col1.metric("Aktivitäten (7d)", f"{act_val:.0f}", delta=f"{act_delta:.1f}%")
col2.metric("Distanz (7d)", f"{dist_val:.1f} km", delta=f"{dist_delta:.1f}%")
col3.metric("Trainingslast (7d)", f"{tss_val:.0f} TSS", delta=f"{tss_delta:.1f}%")
col4.metric("Trainingszeit (7d)", f"{dur_val / 60:.1f} h", delta=f"{dur_delta:.1f}%")

st.divider()

# --- Activity Mix ---
col1, col2 = st.columns(2)
with col1:
    mix = (
        fctx.activities.groupby("activity_type", as_index=False)
        .agg(count=("activity_id", "count"))
        .sort_values("count", ascending=False)
    )
    fig_mix = px.pie(mix, names="activity_type", values="count", title="Aktivitäten nach Typ (Anzahl)")
    fig_mix = apply_premium_theme(fig_mix, graph_type="pie")
    st.plotly_chart(fig_mix, use_container_width=True)

with col2:
    tss_mix = (
        fctx.activities.groupby("activity_type", as_index=False)
        .agg(tss=("training_stress_score", "sum"))
        .sort_values("tss", ascending=False)
    )
    fig_tss = px.bar(
        tss_mix, x="activity_type", y="tss",
        title="Trainingslast (TSS) nach Typ",
        labels={"activity_type": "Typ", "tss": "TSS"},
    )
    fig_tss = apply_premium_theme(fig_tss, graph_type="bar")
    st.plotly_chart(fig_tss, use_container_width=True)

# --- Weekly Aggregation ---
weekly = (
    fctx.activities.set_index("date")
    .resample("W-MON")
    .agg(
        distance_km=("distance_km", "sum"),
        duration_min=("duration_min", "sum"),
        training_stress_score=("training_stress_score", "sum"),
    )
    .reset_index()
)
weekly["week_label"] = (
    (weekly["date"] - pd.Timedelta(days=6)).dt.strftime("%d.%m.")
    + " – "
    + weekly["date"].dt.strftime("%d.%m.")
)

col1, col2 = st.columns(2)
with col1:
    fig_week = px.bar(
        weekly, x="week_label", y="distance_km",
        title="Wöchentliche Distanz",
        labels={"week_label": "Woche", "distance_km": "km"},
    )
    fig_week = apply_premium_theme(fig_week, graph_type="bar")
    st.plotly_chart(fig_week, use_container_width=True)

with col2:
    fig_load = px.bar(
        weekly, x="week_label", y="training_stress_score",
        title="Wöchentliche Trainingslast (TSS)",
        labels={"week_label": "Woche", "training_stress_score": "TSS"},
    )
    fig_load = apply_premium_theme(fig_load, graph_type="bar")
    st.plotly_chart(fig_load, use_container_width=True)

# --- Activity Table ---
st.divider()
st.markdown("### Alle Aktivitäten")
metric_cols = [
    "date", "activity_type", "distance_km", "duration_min",
    "avg_speed_kmh", "avg_hr", "avg_power_w", "training_stress_score",
    "calories", "elevation_gain",
]
visible = [c for c in metric_cols if c in fctx.activities.columns]
rename_display = {
    "date": "Datum", "activity_type": "Typ", "distance_km": "Distanz (km)",
    "duration_min": "Dauer (min)", "avg_speed_kmh": "Ø Speed (km/h)",
    "avg_hr": "Ø HF", "avg_power_w": "Ø Watt", "training_stress_score": "TSS",
    "calories": "Kalorien", "elevation_gain": "Höhenmeter",
}
st.dataframe(
    fctx.activities[visible].sort_values("date", ascending=False).rename(columns=rename_display),
    use_container_width=True,
    hide_index=True,
)
