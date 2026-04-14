import plotly.express as px
import streamlit as st
import sys
from pathlib import Path

# Provide access to the parent folder's modules
sys.path.append(str(Path(__file__).resolve().parents[1]))
from dashboard_data import apply_filters, build_sidebar_filters, load_context, inject_custom_css, apply_premium_theme

st.set_page_config(page_title="Garmin Dashboard: Overview", page_icon="📈", layout="wide")
inject_custom_css()

st.title("📈 Detail-Übersicht")
st.markdown("Willkommen! Nutze die dynamischen Graphen und die Seiten in der Sidebar für tiefe Analysen.")

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
    st.header("Globale Filter")
    
start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="overview_")
fctx = apply_filters(ctx, start_date, end_date, selected_types)

st.markdown("### Dein Zeitraum im Rückblick")
col1, col2, col3, col4, col5 = st.columns(5)

weekly_distance = (
    fctx.daily_training["distance_km"].sum(min_count=1)
    if not fctx.daily_training.empty and "distance_km" in fctx.daily_training
    else 0
)
weekly_tss = (
    fctx.daily_training["training_stress_score"].sum(min_count=1)
    if not fctx.daily_training.empty and "training_stress_score" in fctx.daily_training
    else 0
)
avg_sleep = fctx.days["sleep_hours"].mean() if "sleep_hours" in fctx.days else 0
avg_hrv = fctx.days["avg_hrv"].mean() if "avg_hrv" in fctx.days else 0
avg_recovery = fctx.days["recovery_score"].mean() if "recovery_score" in fctx.days else 0

col1.metric("Aktivitäten", f"{len(fctx.activities)}", help="Gefilterte Aktivitäten im Zeitraum")
col2.metric("Distanz", f"{(weekly_distance or 0):.1f} km", help="Zurückgelegte Kilometer im gewählten Zeitraum")
col3.metric("Trainingslast (TSS)", f"{(weekly_tss or 0):.0f}", help="TSS in diesem Zeitraum")
col4.metric("Avg Sleep", f"{(avg_sleep or 0):.2f} h", help="Durchschnittsdauer Schlaf")
col5.metric("Avg Recovery", f"{(avg_recovery or 0):.1f}", help="Erholungsindex Durchschnitt")

st.divider()

# Organize complexity into Tabs!
tab1, tab2 = st.tabs(["📊 Training & Erholung", "🏆 Highlights"])

with tab1:
    left, right = st.columns(2)
    with left:
        if not fctx.merged_daily.empty:
            cols = [c for c in ["training_stress_score", "recovery_score"] if c in fctx.merged_daily.columns]
            if cols:
                df_plot = fctx.merged_daily.rename(columns={
                    "training_stress_score": "Trainingslast",
                    "recovery_score": "Erholung"
                })
                fig = px.line(
                    df_plot, 
                    x="date", 
                    y=[c for c in ["Trainingslast", "Erholung"] if c in df_plot.columns], 
                    title="Load vs. Recovery"
                )
                fig = apply_premium_theme(fig)
                st.plotly_chart(fig, use_container_width=True)

    with right:
        if not fctx.days.empty and {"sleep_score", "avg_hrv", "avg_stress"}.intersection(fctx.days.columns):
            available = [c for c in ["sleep_score", "avg_hrv", "avg_stress"] if c in fctx.days.columns]
            df_plot = fctx.days.rename(columns={
                "sleep_score": "Schlaf-Score",
                "avg_hrv": "HRV",
                "avg_stress": "Stress"
            })
            display_cols = [c for c in ["Schlaf-Score", "HRV", "Stress"] if c in df_plot.columns]
            fig = px.line(df_plot, x="date", y=display_cols, title="Erholungs-Indikatoren")
            fig = apply_premium_theme(fig)
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    if fctx.activities.empty:
        st.info("Keine Aktivitäten im gewählten Zeitraum.")
    else:
        best_distance = fctx.activities.sort_values("distance_km", ascending=False).head(1)
        best_tss = fctx.activities.sort_values("training_stress_score", ascending=False).head(1)
        
        c1, c2 = st.columns(2)
        with c1:
            if not best_distance.empty:
                row = best_distance.iloc[0]
                with st.container(border=True):
                    st.markdown("### Längste Aktivität 🏃‍♂️")
                    st.write(f"**Typ**: {row.get('activity_type', 'Unbekannt')}")
                    st.write(f"**Datum**: {row['date'].date()}")
                    st.metric("Distanz", f"{row.get('distance_km', 0):.2f} km")
        with c2:
            if not best_tss.empty:
                row = best_tss.iloc[0]
                with st.container(border=True):
                    st.markdown("### Höchste Belastung 💥")
                    st.write(f"**Typ**: {row.get('activity_type', 'Unbekannt')}")
                    st.write(f"**Datum**: {row['date'].date()}")
                    st.metric("Score", f"{row.get('training_stress_score', 0):.0f} TSS")
