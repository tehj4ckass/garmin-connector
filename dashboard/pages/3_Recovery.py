import plotly.express as px
import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import apply_filters, build_sidebar_filters, load_context


st.set_page_config(page_title="Recovery", page_icon="😴", layout="wide")
st.title("😴 Recovery")

ctx = load_context()
with st.sidebar:
    st.header("Global Filters")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="recovery_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.days.empty:
    st.info("No recovery data in selected range.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Avg Sleep", f"{fctx.days['sleep_hours'].mean() if 'sleep_hours' in fctx.days else 0:.2f} h")
col2.metric("Avg HRV", f"{fctx.days['avg_hrv'].mean() if 'avg_hrv' in fctx.days else 0:.1f}")
col3.metric("Avg Resting HR", f"{fctx.days['resting_hr'].mean() if 'resting_hr' in fctx.days else 0:.1f}")
col4.metric("Avg Recovery", f"{fctx.days['recovery_score'].mean() if 'recovery_score' in fctx.days else 0:.1f}")

trend_cols = [c for c in ["sleep_hours", "sleep_score", "avg_hrv", "resting_hr", "avg_stress", "recovery_score"] if c in fctx.days.columns]
fig_recovery = px.line(fctx.days, x="date", y=trend_cols, title="Recovery Trends")
st.plotly_chart(fig_recovery, use_container_width=True)

if {"body_battery_high", "body_battery_low"}.issubset(fctx.days.columns):
    fig_bb = px.line(
        fctx.days,
        x="date",
        y=["body_battery_high", "body_battery_low"],
        title="Body Battery High/Low",
    )
    st.plotly_chart(fig_bb, use_container_width=True)

st.dataframe(fctx.days.sort_values("date", ascending=False), use_container_width=True)
