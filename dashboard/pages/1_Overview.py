import plotly.express as px
import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import apply_filters, build_sidebar_filters, load_context


st.set_page_config(page_title="Overview", page_icon="📈", layout="wide")
st.title("📈 Overview")

ctx = load_context()
with st.sidebar:
    st.header("Global Filters")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="overview_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

col1, col2, col3, col4, col5 = st.columns(5)
weekly_distance = (
    fctx.daily_training.tail(7)["distance_km"].sum(min_count=1)
    if not fctx.daily_training.empty and "distance_km" in fctx.daily_training
    else 0
)
weekly_tss = (
    fctx.daily_training.tail(7)["training_stress_score"].sum(min_count=1)
    if not fctx.daily_training.empty and "training_stress_score" in fctx.daily_training
    else 0
)
avg_sleep = fctx.days["sleep_hours"].mean() if "sleep_hours" in fctx.days else 0
avg_hrv = fctx.days["avg_hrv"].mean() if "avg_hrv" in fctx.days else 0
avg_recovery = fctx.days["recovery_score"].mean() if "recovery_score" in fctx.days else 0

col1.metric("Activities", f"{len(fctx.activities)}")
col2.metric("Weekly Distance", f"{(weekly_distance or 0):.1f} km")
col3.metric("Weekly Load (TSS)", f"{(weekly_tss or 0):.0f}")
col4.metric("Avg Sleep", f"{(avg_sleep or 0):.2f} h")
col5.metric("Avg Recovery", f"{(avg_recovery or 0):.1f}")

left, right = st.columns(2)
with left:
    if not fctx.merged_daily.empty:
        cols = [c for c in ["training_stress_score", "recovery_score"] if c in fctx.merged_daily.columns]
        if cols:
            fig = px.line(fctx.merged_daily, x="date", y=cols, title="Training Load vs Recovery")
            st.plotly_chart(fig, use_container_width=True)

with right:
    if not fctx.days.empty and {"sleep_score", "avg_hrv", "avg_stress"}.intersection(fctx.days.columns):
        available = [c for c in ["sleep_score", "avg_hrv", "avg_stress"] if c in fctx.days.columns]
        fig = px.line(fctx.days, x="date", y=available, title="Recovery Signals")
        st.plotly_chart(fig, use_container_width=True)

st.subheader("Highlights")
if fctx.activities.empty:
    st.info("No activities in selected range.")
else:
    best_distance = fctx.activities.sort_values("distance_km", ascending=False).head(1)
    best_tss = fctx.activities.sort_values("training_stress_score", ascending=False).head(1)
    c1, c2 = st.columns(2)
    with c1:
        if not best_distance.empty:
            row = best_distance.iloc[0]
            st.write(
                f"Longest activity: `{row.get('activity_type', 'Unknown')}` on "
                f"`{row['date'].date()}` - `{row.get('distance_km', 0):.2f} km`"
            )
    with c2:
        if not best_tss.empty:
            row = best_tss.iloc[0]
            st.write(
                f"Highest load: `{row.get('activity_type', 'Unknown')}` on "
                f"`{row['date'].date()}` - `TSS {row.get('training_stress_score', 0):.0f}`"
            )
