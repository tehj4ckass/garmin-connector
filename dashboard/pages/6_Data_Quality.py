import streamlit as st
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import load_context


st.set_page_config(page_title="Data Quality", page_icon="🧪", layout="wide")
st.title("🧪 Data Quality")

ctx = load_context()

st.subheader("Data Sources")
st.write(f"- Fitness JSON: `{ctx.fitness_path}`")
st.write(f"- Health JSON: `{ctx.health_path}`")
st.write(f"- Fitness schema_version: `{ctx.fitness_doc.get('schema_version')}`")
st.write(f"- Health schema_version: `{ctx.health_doc.get('schema_version')}`")
st.write(f"- Fitness generated_at: `{ctx.fitness_doc.get('generated_at')}`")
st.write(f"- Health generated_at: `{ctx.health_doc.get('generated_at')}`")

st.subheader("Row Counts")
c1, c2, c3 = st.columns(3)
c1.metric("Activities", f"{len(ctx.activities)}")
c2.metric("Health Days", f"{len(ctx.days)}")
c3.metric("Merged Daily Rows", f"{len(ctx.merged_daily)}")

st.subheader("Missing Values")
q1, q2 = st.columns(2)
with q1:
    st.caption("Activities")
    if ctx.activities.empty:
        st.write("No activity data loaded.")
    else:
        st.dataframe(ctx.activities.isna().sum().rename("missing_count"))
with q2:
    st.caption("Health days")
    if ctx.days.empty:
        st.write("No health data loaded.")
    else:
        st.dataframe(ctx.days.isna().sum().rename("missing_count"))

st.subheader("Duplicate Activity IDs")
if ctx.activities.empty or "activity_id" not in ctx.activities.columns:
    st.write("No activity IDs available.")
else:
    dup = ctx.activities[ctx.activities.duplicated(subset=["activity_id"], keep=False)].sort_values("activity_id")
    if dup.empty:
        st.success("No duplicate `activity_id` values found.")
    else:
        st.warning(f"Found {len(dup)} duplicated rows.")
        st.dataframe(dup[["date", "activity_id", "activity_type"]], use_container_width=True)
