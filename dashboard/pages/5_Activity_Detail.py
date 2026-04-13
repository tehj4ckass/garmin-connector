import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import apply_filters, build_sidebar_filters, load_context


st.set_page_config(page_title="Activity Detail", page_icon="🔍", layout="wide")
st.title("🔍 Activity Detail")

ctx = load_context()
with st.sidebar:
    st.header("Global Filters")
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="detail_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.activities.empty:
    st.info("No activities available for selected filters.")
    st.stop()

options_df = fctx.activities.sort_values("date", ascending=False).copy()
options_df["label"] = options_df.apply(
    lambda r: f"{r['date'].date()} | {r.get('activity_type', 'Unknown')} | id={r.get('activity_id', 'n/a')}",
    axis=1,
)
selected_label = st.selectbox("Choose activity", options_df["label"].tolist())
selected = options_df[options_df["label"] == selected_label].iloc[0]

st.subheader("Core Metrics")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Distance (km)", f"{selected.get('distance_km', 0) or 0:.2f}")
c2.metric("Duration (min)", f"{selected.get('duration_min', 0) or 0:.1f}")
c3.metric("Avg HR", f"{selected.get('avg_hr', 0) or 0:.0f}")
c4.metric("TSS", f"{selected.get('training_stress_score', 0) or 0:.0f}")

st.subheader("All Fields")
st.json({k: (None if str(v) == "nan" else v) for k, v in selected.to_dict().items()})

if "hr_zones" in selected and selected["hr_zones"] not in (None, "", {}):
    st.subheader("HR Zones Raw Data")
    st.json(selected["hr_zones"])
