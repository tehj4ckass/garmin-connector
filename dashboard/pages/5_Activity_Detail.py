import streamlit as st
from pathlib import Path
import sys
import math

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

def _clean_value(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _clean_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_value(v) for v in value]
    return value


def _format_metric(value, fmt: str):
    cleaned = _clean_value(value)
    if cleaned is None:
        return "-"
    try:
        return format(cleaned, fmt)
    except Exception:
        return str(cleaned)


df = fctx.activities.sort_values("date", ascending=False).copy()
df["activity_key"] = df.apply(
    lambda r: f"{r.get('activity_id', 'n/a')}::{r['date']}::{r.get('activity_type', 'Unknown')}",
    axis=1,
)
df["display_label"] = df.apply(
    lambda r: (
        f"{r['date'].date()} | {r.get('activity_type', 'Unknown')} | "
        f"{_format_metric(r.get('distance_km'), '.2f')} km | id={r.get('activity_id', 'n/a')}"
    ),
    axis=1,
)

top1, top2, top3 = st.columns(3)
top1.metric("Activities", f"{len(df)}")
top2.metric("Distance (km)", _format_metric(df["distance_km"].sum(min_count=1) if "distance_km" in df.columns else None, ".2f"))
top3.metric("Duration (h)", _format_metric((df["duration_min"].sum(min_count=1) / 60) if "duration_min" in df.columns else None, ".1f"))

search_term = st.text_input("Search in activity type or id", placeholder="e.g. running or 123456")
filtered_df = df
if search_term.strip():
    needle = search_term.strip().lower()
    filtered_df = df[
        df.get("activity_type", "").astype(str).str.lower().str.contains(needle, na=False)
        | df.get("activity_id", "").astype(str).str.lower().str.contains(needle, na=False)
    ]

if filtered_df.empty:
    st.info("No activities match your search.")
    st.stop()

left, right = st.columns([1.1, 1.4], gap="large")

with left:
    st.subheader("Activity List")
    table_cols = [c for c in ["date", "activity_type", "distance_km", "duration_min", "training_stress_score", "activity_id"] if c in filtered_df.columns]
    st.dataframe(
        filtered_df[table_cols].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )
    selected_key = st.selectbox(
        "Select activity",
        filtered_df["activity_key"].tolist(),
        format_func=lambda key: filtered_df.loc[filtered_df["activity_key"] == key, "display_label"].iloc[0],
    )

selected = filtered_df[filtered_df["activity_key"] == selected_key].iloc[0]

with right:
    st.subheader(f"{_clean_value(selected.get('activity_type')) or 'Activity'} on {selected['date'].date()}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Distance (km)", _format_metric(selected.get("distance_km"), ".2f"))
    m2.metric("Duration (min)", _format_metric(selected.get("duration_min"), ".1f"))
    m3.metric("Avg HR", _format_metric(selected.get("avg_hr"), ".0f"))
    m4.metric("TSS", _format_metric(selected.get("training_stress_score"), ".0f"))

    st.markdown("#### Details")
    d1, d2 = st.columns(2)
    with d1:
        st.write("**Date**", _clean_value(selected.get("date")))
        st.write("**Activity ID**", _clean_value(selected.get("activity_id")))
        st.write("**Type**", _clean_value(selected.get("activity_type")))
        st.write("**Average Speed (km/h)**", _format_metric(selected.get("avg_speed_kmh"), ".2f"))
    with d2:
        st.write("**Max HR**", _format_metric(selected.get("max_hr"), ".0f"))
        st.write("**Calories**", _format_metric(selected.get("calories"), ".0f"))
        st.write("**Elevation Gain (m)**", _format_metric(selected.get("elevation_gain_m"), ".0f"))
        st.write("**Training Effect**", _format_metric(selected.get("training_effect"), ".2f"))

    with st.expander("Show raw activity JSON", expanded=False):
        st.json({k: _clean_value(v) for k, v in selected.to_dict().items()})

    if "hr_zones" in selected and selected["hr_zones"] not in (None, "", {}):
        with st.expander("Show HR Zones", expanded=False):
            st.json(_clean_value(selected["hr_zones"]))
