import plotly.express as px
import streamlit as st

from dashboard_data import apply_filters, build_sidebar_filters, load_context


st.set_page_config(page_title="Garmin Dashboard", page_icon="⌚", layout="wide")

st.title("⌚ Garmin Dashboard")
st.caption("Overview and quick status. Use the pages in the sidebar for deep analysis.")

try:
    ctx = load_context()
except FileNotFoundError as exc:
    st.error(str(exc))
    st.info("Run the connector first to create `fitness_data.json` and `health_data.json`.")
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Unable to load dashboard data: {exc}")
    st.stop()

with st.sidebar:
    st.header("Global Filters")
filters = build_sidebar_filters(ctx, key_prefix="home_")
if not filters:
    st.warning("No data available yet.")
    st.stop()
start_date, end_date, selected_types = filters
fctx = apply_filters(ctx, start_date, end_date, selected_types)

col1, col2, col3, col4 = st.columns(4)
distance_sum = fctx.activities["distance_km"].sum() if not fctx.activities.empty and "distance_km" in fctx.activities else 0
duration_sum = fctx.activities["duration_min"].sum() if not fctx.activities.empty and "duration_min" in fctx.activities else 0

sleep_series = fctx.days["sleep_hours"].dropna() if "sleep_hours" in fctx.days else []
sleep_avg = sleep_series.mean() if len(sleep_series) > 0 else 0

recovery_series = fctx.days["recovery_score"].dropna() if "recovery_score" in fctx.days else []
recovery_avg = recovery_series.mean() if len(recovery_series) > 0 else 0

col1.metric("Activities", f"{len(fctx.activities)}")
col2.metric("Distance (km)", f"{(distance_sum or 0):.1f}")
col3.metric("Duration (min)", f"{(duration_sum or 0):.0f}")
col4.metric("Recovery Score", f"{(recovery_avg or 0):.1f}")

st.metric("Avg Sleep (h)", f"{(sleep_avg or 0):.2f}")

if not fctx.merged_daily.empty:
    plot_cols = [c for c in ["training_stress_score", "recovery_score", "sleep_score"] if c in fctx.merged_daily.columns]
    if plot_cols:
        fig = px.line(fctx.merged_daily, x="date", y=plot_cols, title="Training and Recovery Trends")
        st.plotly_chart(fig, use_container_width=True)

st.markdown(
    "### Seiten\n"
    "- `Overview`: KPI + Highlights\n"
    "- `Training`: Load, Aktivitätsmix, Wochenansichten\n"
    "- `Recovery`: Schlaf, HRV, Stress, Body Battery\n"
    "- `Correlations`: Zusammenhänge Training <-> Erholung\n"
    "- `Activity Detail`: Drilldown pro Aktivität\n"
    "- `Data Quality`: Datenquellen und Vollständigkeit"
)
