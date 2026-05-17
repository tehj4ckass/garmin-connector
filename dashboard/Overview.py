import plotly.express as px
import streamlit as st
import sys
from pathlib import Path

# Provide access to the parent folder's modules
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



try:
    ctx = load_context()
except Exception as exc:
    st.error(f"Fehler beim Laden der Daten: {exc}")
    st.stop()

render_header("📈 Deine Fitness im Überblick", "Analysiere deine Leistung und Erholung über die Zeit.")

with st.sidebar:
    st.header("Globale Filter")
    start_date, end_date, selected_types = build_sidebar_filters(ctx, key_prefix="overview_")

fctx = apply_filters(ctx, start_date, end_date, selected_types)

# --- Metric Section ---
st.markdown("### Aktuelle Trends (vs. Vorwoche)")
m1, m2, m3, m4, m5 = st.columns(5)

# Calculate Trends
act_count, act_delta = calculate_weekly_trend(fctx.activities, "activity_id", agg="count")
dist_val, dist_delta = calculate_weekly_trend(fctx.daily_training, "distance_km", agg="sum")
tss_val, tss_delta = calculate_weekly_trend(fctx.daily_training, "training_stress_score", agg="sum")
sleep_val, sleep_delta = calculate_weekly_trend(fctx.days, "sleep_hours", agg="mean")
recov_val, recov_delta = calculate_weekly_trend(fctx.days, "recovery_score", agg="mean")

m1.metric("Aktivitäten (7d)", f"{act_count:.0f}", delta=f"{act_delta:.1f}%")
m2.metric("Distanz (7d)", f"{dist_val:.1f} km", delta=f"{dist_delta:.1f}%")
m3.metric("Trainingslast (7d)", f"{tss_val:.0f} TSS", delta=f"{tss_delta:.1f}%")
m4.metric("Ø Schlaf (7d)", f"{sleep_val:.1f} h", delta=f"{sleep_delta:.1f}%")
m5.metric("Ø Erholung (7d)", f"{recov_val:.1f}", delta=f"{recov_delta:.1f}%")

st.divider()

# --- Main Analysis Section ---
tab1, tab2 = st.tabs(["📊 Training & Erholung", "🏆 Highlights"])

with tab1:
    l_col, r_col = st.columns(2)
    with l_col:
        if not fctx.merged_daily.empty:
            rename_map = {
                "training_stress_score": "Belastung (TSS)",
                "recovery_score": "Erholung",
                "recovery_7d": "Erholung (7d Ø)",
            }
            plot_cols = [c for c in ["training_stress_score", "recovery_score", "recovery_7d"] if c in fctx.merged_daily.columns]
            df_plot = fctx.merged_daily.rename(columns=rename_map)
            fig = px.line(df_plot, x="date", y=[rename_map[c] for c in plot_cols], title="Belastung vs. Erholung")
            st.plotly_chart(apply_premium_theme(fig), use_container_width=True)
            avg_recov = fctx.days["recovery_score"].mean() if not fctx.days.empty else 0
            threshold = 70
            if avg_recov >= threshold:
                st.success(f"💡 Deine Ø Erholung liegt bei {avg_recov:.0f} — guter Zeitpunkt für intensive Einheiten.")
            else:
                st.warning(f"💡 Deine Ø Erholung liegt bei {avg_recov:.0f} — plane mehr Regeneration ein.")
            
    with r_col:
        if not fctx.days.empty:
            df_plot = fctx.days.rename(columns={
                "sleep_score": "Schlaf-Score",
                "avg_hrv": "HRV",
                "avg_stress": "Stress"
            })
            fig = px.line(df_plot, x="date", y=["Schlaf-Score", "HRV"], title="Vitalwerte")
            st.plotly_chart(apply_premium_theme(fig), use_container_width=True)

with tab2:
    if fctx.activities.empty:
        st.info("Keine Aktivitäten im gewählten Zeitraum.")
    else:
        c1, c2 = st.columns(2)
        best_dist = fctx.activities.sort_values("distance_km", ascending=False).iloc[0]
        best_tss = fctx.activities.sort_values("training_stress_score", ascending=False).iloc[0]
        
        with c1:
            with st.container(border=True):
                st.markdown("### 🏃‍♂️ Weiteste Strecke")
                st.write(f"**{best_dist['activity_type']}** am {best_dist['date'].date()}")
                st.metric("Distanz", f"{best_dist['distance_km']:.2f} km")
        
        with c2:
            with st.container(border=True):
                st.markdown("### 💥 Intensivste Einheit")
                st.write(f"**{best_tss['activity_type']}** am {best_tss['date'].date()}")
                st.metric("Score", f"{best_tss['training_stress_score']:.0f} TSS")
