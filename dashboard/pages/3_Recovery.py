import plotly.express as px
import plotly.graph_objects as go
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

st.set_page_config(page_title="Erholung", page_icon="😴", layout="wide")
inject_custom_css()
render_header("😴 Erholung & Schlaf", "Wie gut regeneriert sich dein Körper?")

ctx = load_context()
with st.sidebar:
    st.header("Filter")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="recovery_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.days.empty:
    st.info("Keine Erholungsdaten im gewählten Zeitraum.")
    st.stop()

# --- Metric Cards with Trends ---
st.markdown("### Aktuelle Trends (vs. Vorwoche)")
col1, col2, col3, col4 = st.columns(4)

sleep_val, sleep_delta = calculate_weekly_trend(fctx.days, "sleep_hours", agg="mean")
hrv_val, hrv_delta = calculate_weekly_trend(fctx.days, "avg_hrv", agg="mean")
rhr_val, rhr_delta = calculate_weekly_trend(fctx.days, "resting_hr", agg="mean")
recov_val, recov_delta = calculate_weekly_trend(fctx.days, "recovery_score", agg="mean")

col1.metric("Ø Schlaf", f"{sleep_val:.1f} h", delta=f"{sleep_delta:.1f}%")
col2.metric("Ø HRV", f"{hrv_val:.1f}", delta=f"{hrv_delta:.1f}%")
col3.metric("Ø Ruhe-HF", f"{rhr_val:.1f} bpm", delta=f"{-rhr_delta:.1f}%", delta_color="inverse")
col4.metric("Ø Erholung", f"{recov_val:.1f}", delta=f"{recov_delta:.1f}%")

st.divider()

# --- Charts ---
tab1, tab2 = st.tabs(["📈 Erholungs-Trend", "💤 Schlaf & HRV"])

with tab1:
    if "recovery_score" in fctx.days.columns:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=fctx.days["date"],
            y=fctx.days["recovery_score"],
            name="Erholung (täglich)",
            mode="lines+markers",
            line=dict(color="#6366f1", width=2, dash="dot"),
            marker=dict(size=5, opacity=0.6),
        ))
        if "recovery_7d" in fctx.days.columns:
            fig.add_trace(go.Scatter(
                x=fctx.days["date"],
                y=fctx.days["recovery_7d"],
                name="7-Tage Ø",
                mode="lines",
                line=dict(color="#00ccff", width=3, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(0, 204, 255, 0.07)",
            ))
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(16,185,129,0.5)", annotation_text="Gut (70)")
        fig.add_hline(y=50, line_dash="dash", line_color="rgba(245,158,11,0.5)", annotation_text="Moderat (50)")
        fig.update_layout(title="Erholungs-Score mit 7-Tage-Trend", yaxis=dict(range=[0, 100]))
        st.plotly_chart(apply_premium_theme(fig), use_container_width=True)

    if {"body_battery_high", "body_battery_low"}.issubset(fctx.days.columns):
        df_bb = fctx.days.rename(columns={
            "body_battery_high": "Body Battery Max",
            "body_battery_low": "Body Battery Min"
        })
        fig_bb = px.line(df_bb, x="date", y=["Body Battery Max", "Body Battery Min"], title="Body Battery")
        st.plotly_chart(apply_premium_theme(fig_bb, graph_type="line"), use_container_width=True)

with tab2:
    l_col, r_col = st.columns(2)
    with l_col:
        sleep_cols = {c: v for c, v in {"sleep_hours": "Schlaf (h)", "sleep_score": "Schlaf-Score"}.items() if c in fctx.days.columns}
        if sleep_cols:
            fig = px.line(
                fctx.days.rename(columns=sleep_cols),
                x="date", y=list(sleep_cols.values()),
                title="Schlaf",
            )
            st.plotly_chart(apply_premium_theme(fig, graph_type="line"), use_container_width=True)

    with r_col:
        hrv_cols = {c: v for c, v in {"avg_hrv": "HRV", "resting_hr": "Ruhe-HF"}.items() if c in fctx.days.columns}
        if hrv_cols:
            fig = px.line(
                fctx.days.rename(columns=hrv_cols),
                x="date", y=list(hrv_cols.values()),
                title="HRV & Ruhe-Herzfrequenz",
            )
            st.plotly_chart(apply_premium_theme(fig, graph_type="line"), use_container_width=True)

    if "avg_stress" in fctx.days.columns:
        fig_stress = px.line(fctx.days, x="date", y="avg_stress", title="Ø Stress", labels={"avg_stress": "Stress-Level"})
        st.plotly_chart(apply_premium_theme(fig_stress, graph_type="line"), use_container_width=True)

# --- Last 7 days summary ---
st.divider()
st.markdown("### Letzte 7 Tage")
last7 = fctx.days.sort_values("date", ascending=False).head(7)
display_cols = [c for c in ["date", "recovery_score", "sleep_hours", "sleep_score", "avg_hrv", "resting_hr", "avg_stress", "body_battery_high"] if c in last7.columns]
rename_display = {
    "date": "Datum", "recovery_score": "Erholung", "sleep_hours": "Schlaf (h)",
    "sleep_score": "Schlaf-Score", "avg_hrv": "HRV", "resting_hr": "Ruhe-HF",
    "avg_stress": "Ø Stress", "body_battery_high": "Body Battery",
}
st.dataframe(
    last7[display_cols].rename(columns=rename_display),
    use_container_width=True,
    hide_index=True,
)
