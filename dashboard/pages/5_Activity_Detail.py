import streamlit as st
from pathlib import Path
import sys
import math
import plotly.express as px
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import (
    apply_filters, 
    build_sidebar_filters, 
    load_context, 
    inject_custom_css, 
    apply_premium_theme,
    render_header
)

st.set_page_config(page_title="Aktivitäts-Details", page_icon="🔍", layout="wide")
inject_custom_css()

ctx = load_context()
render_header("🔍 Aktivitäts-Details", "Detaillierte Analyse einzelner Einheiten.")

with st.sidebar:
    st.header("Filter")
    start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="detail_")

fctx = apply_filters(ctx, start_date, end_date, selected_types)

if fctx.activities.empty:
    st.info("Keine Aktivitäten für die gewählten Filter gefunden.")
    st.stop()

def _clean_value(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value

df = fctx.activities.sort_values("date", ascending=False).copy()
df["display_label"] = df.apply(
    lambda r: f"{r['date'].date()} | {r.get('activity_type', 'Unknown')} | {r.get('distance_km', 0):.2f} km",
    axis=1
)

left_nav, right_content = st.columns([1, 2], gap="large")

with left_nav:
    st.subheader("Auswahl")
    selected_label = st.selectbox(
        "Aktivität wählen",
        df["display_label"].tolist()
    )
    selected = df[df["display_label"] == selected_label].iloc[0]
    
    with st.container(border=True):
        st.markdown(f"### {selected['activity_type']}")
        st.write(f"📅 **Datum**: {selected['date'].date()}")
        st.write(f"🆔 **ID**: `{selected.get('activity_id', 'n/a')}`")
        st.divider()
        st.metric("Distanz", f"{selected.get('distance_km', 0):.2f} km")
        st.metric("Dauer", f"{selected.get('duration_min', 0):.1f} min")

with right_content:
    st.subheader("Leistungsdaten")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ø Puls", f"{selected.get('avg_hr', 0):.0f} bpm")
    m2.metric("Max Puls", f"{selected.get('max_hr', 0):.0f} bpm")
    m3.metric("TSS", f"{selected.get('training_stress_score', 0):.0f}")
    m4.metric("Kalorien", f"{selected.get('calories', 0):.0f} kcal")

    # HR Zones Visualization
    hr_zones = selected.get("hr_zones")
    if hr_zones and isinstance(hr_zones, dict):
        st.markdown("#### Herzfrequenz-Zonen")
        # Transform dict to DataFrame for plotting
        z_df = pd.DataFrame([
            {"Zone": k.replace("zone", "Z"), "Minuten": v / 60 if v else 0} 
            for k, v in hr_zones.items() if "zone" in k
        ])
        if not z_df.empty:
            fig = px.bar(z_df, x="Zone", y="Minuten", color="Zone", 
                         color_discrete_sequence=['#94a3b8', '#38bdf8', '#10b981', '#f59e0b', '#ef4444'])
            fig = apply_premium_theme(fig, graph_type="bar")
            st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("#### Weitere Details")
    d1, d2 = st.columns(2)
    with d1:
        st.write("**Ø Geschwindigkeit**", f"{selected.get('avg_speed_kmh', 0):.2f} km/h")
        st.write("**Höhenmeter**", f"{selected.get('elevation_gain', 0):.0f} m")
    with d2:
        st.write("**Training Effect**", f"{selected.get('training_effect', 0):.1f}")
        st.write("**Ø Leistung**", f"{selected.get('avg_power_w', 0):.0f} W")

    with st.expander("Rohdaten (JSON)"):
        st.json(selected.to_dict())
