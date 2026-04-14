import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st


@dataclass
class DashboardContext:
    fitness_doc: dict
    health_doc: dict
    fitness_path: Path
    health_path: Path
    activities: pd.DataFrame
    days: pd.DataFrame
    daily_training: pd.DataFrame
    merged_daily: pd.DataFrame


def _safe_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _candidate_paths(filename: str) -> list[Path]:
    data_dir = os.getenv("DASHBOARD_DATA_DIR", "").strip()
    cwd = Path.cwd()
    candidates = []
    if data_dir:
        candidates.append(Path(data_dir) / filename)
    candidates.append(cwd / filename)
    candidates.append(cwd / "data" / filename)
    return candidates


def _resolve_file(filename: str) -> Path | None:
    for path in _candidate_paths(filename):
        if path.exists():
            return path
    return None


def _load_json_document(filename: str) -> tuple[dict, Path]:
    resolved = _resolve_file(filename)
    if not resolved:
        searched = ", ".join(str(p) for p in _candidate_paths(filename))
        raise FileNotFoundError(f"{filename} not found. Checked: {searched}")

    with resolved.open("r", encoding="utf-8") as handle:
        return json.load(handle), resolved


def _prepare_activities_dataframe(doc: dict) -> pd.DataFrame:
    activities = doc.get("activities", [])
    if not activities:
        return pd.DataFrame()

    df = pd.DataFrame(activities).copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")

    numeric_cols = [
        "distance_km",
        "duration_min",
        "moving_time_min",
        "avg_speed_kmh",
        "avg_hr",
        "max_hr",
        "avg_power_w",
        "training_stress_score",
        "calories",
        "elevation_gain",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["date"]).sort_values("date")


def _prepare_days_dataframe(doc: dict) -> pd.DataFrame:
    days = doc.get("days", [])
    if not days:
        return pd.DataFrame()

    df = pd.DataFrame(days).copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce")

    numeric_cols = [
        "resting_hr",
        "avg_hrv",
        "avg_stress",
        "max_stress",
        "body_battery_high",
        "body_battery_low",
        "sleep_hours",
        "sleep_score",
        "steps",
        "intensity_minutes",
        "active_calories",
        "total_calories",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["date"]).sort_values("date")


def _daily_training_aggregation(df_activities: pd.DataFrame) -> pd.DataFrame:
    if df_activities.empty:
        return pd.DataFrame(columns=["date", "activity_count", "distance_km", "duration_min", "training_stress_score"])

    daily = (
        df_activities.groupby("date", as_index=False)
        .agg(
            activity_count=("activity_id", "count"),
            distance_km=("distance_km", "sum"),
            duration_min=("duration_min", "sum"),
            training_stress_score=("training_stress_score", "sum"),
        )
        .sort_values("date")
    )
    return daily


def _recovery_score_row(row: pd.Series) -> float | None:
    sleep_score = _safe_float(row.get("sleep_score"))
    hrv = _safe_float(row.get("avg_hrv"))
    stress = _safe_float(row.get("avg_stress"))
    resting_hr = _safe_float(row.get("resting_hr"))

    parts = []
    if sleep_score is not None:
        parts.append(max(0.0, min(100.0, sleep_score)) * 0.35)
    if hrv is not None:
        hrv_norm = max(0.0, min(100.0, hrv))
        parts.append(hrv_norm * 0.25)
    if stress is not None:
        parts.append(max(0.0, min(100.0, 100 - stress)) * 0.20)
    if resting_hr is not None:
        rhr_norm = max(0.0, min(100.0, 100 - (resting_hr - 35) * 2))
        parts.append(rhr_norm * 0.20)

    if not parts:
        return None
    return round(sum(parts), 2)


def _add_recovery_metrics(df_days: pd.DataFrame) -> pd.DataFrame:
    if df_days.empty:
        return df_days
    result = df_days.copy()
    result["recovery_score"] = result.apply(_recovery_score_row, axis=1)
    result["recovery_7d"] = result["recovery_score"].rolling(7, min_periods=1).mean()
    return result


def _merged_daily(df_days: pd.DataFrame, df_daily_training: pd.DataFrame) -> pd.DataFrame:
    if df_days.empty and df_daily_training.empty:
        return pd.DataFrame()

    days_cols = ["date", "recovery_score", "sleep_hours", "sleep_score", "avg_hrv", "resting_hr", "avg_stress"]
    existing_days_cols = [c for c in days_cols if c in df_days.columns]
    train_cols = ["date", "activity_count", "distance_km", "duration_min", "training_stress_score"]
    existing_train_cols = [c for c in train_cols if c in df_daily_training.columns]

    return pd.merge(
        df_days[existing_days_cols] if existing_days_cols else pd.DataFrame(columns=["date"]),
        df_daily_training[existing_train_cols] if existing_train_cols else pd.DataFrame(columns=["date"]),
        on="date",
        how="outer",
    ).sort_values("date")


def filter_dateframe(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    if df.empty:
        return df
    mask = (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)
    return df.loc[mask].copy()


def apply_filters(ctx: DashboardContext, start_date, end_date, selected_types: list[str]) -> DashboardContext:
    activities = filter_dateframe(ctx.activities, start_date, end_date)
    days = filter_dateframe(ctx.days, start_date, end_date)

    if selected_types and not activities.empty and "activity_type" in activities.columns:
        activities = activities[activities["activity_type"].isin(selected_types)]

    daily_training = _daily_training_aggregation(activities)
    merged_daily = _merged_daily(days, daily_training)

    return DashboardContext(
        fitness_doc=ctx.fitness_doc,
        health_doc=ctx.health_doc,
        fitness_path=ctx.fitness_path,
        health_path=ctx.health_path,
        activities=activities,
        days=days,
        daily_training=daily_training,
        merged_daily=merged_daily,
    )


def all_dates(ctx: DashboardContext) -> list:
    dates = []
    if not ctx.activities.empty:
        dates.extend(ctx.activities["date"].dt.date.tolist())
    if not ctx.days.empty:
        dates.extend(ctx.days["date"].dt.date.tolist())
    return dates


def activity_types(ctx: DashboardContext) -> list[str]:
    if ctx.activities.empty or "activity_type" not in ctx.activities.columns:
        return []
    return sorted(ctx.activities["activity_type"].dropna().astype(str).unique().tolist())


from datetime import timedelta

def build_sidebar_filters(ctx: DashboardContext, *, key_prefix: str = ""):
    dates = all_dates(ctx)
    if not dates:
        return None

    min_date = min(dates)
    max_date = max(dates)
    default_start = max(min_date, max_date - timedelta(days=30))

    date_range = st.sidebar.date_input(
        "Zeitraum",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
        key=f"{key_prefix}date_range",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = default_start, max_date

    types = activity_types(ctx)
    selected_types = st.sidebar.multiselect(
        "Activity types",
        options=types,
        default=types,
        key=f"{key_prefix}activity_types",
    )
    return start_date, end_date, selected_types


@st.cache_data(ttl=120)
def load_context() -> DashboardContext:
    fitness_doc, fitness_path = _load_json_document("fitness_data.json")
    health_doc, health_path = _load_json_document("health_data.json")

    activities = _prepare_activities_dataframe(fitness_doc)
    days = _add_recovery_metrics(_prepare_days_dataframe(health_doc))
    daily_training = _daily_training_aggregation(activities)
    merged_daily = _merged_daily(days, daily_training)

    return DashboardContext(
        fitness_doc=fitness_doc,
        health_doc=health_doc,
        fitness_path=fitness_path,
        health_path=health_path,
        activities=activities,
        days=days,
        daily_training=daily_training,
        merged_daily=merged_daily,
    )


def inject_custom_css():
    css_path = Path(__file__).parent / "style.css"
    if css_path.exists():
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def apply_premium_theme(fig, graph_type="line"):
    """Applies modern dark-mode formatting to Plotly figures."""
    
    # 1. Füge sichtbare Punkte ("markers") und die echten Zahlenwerte ("text") hinzu
    if graph_type == "line":
        fig.update_traces(
            mode="lines+markers+text",
            texttemplate="%{y:.0f}",
            textposition="top center",
            marker=dict(size=8),
            selector=dict(type="scatter", mode="lines") # Only target lines
        )
        # Ensure we also hit default px.line which may lack explicit mode
        for trace in fig.data:
            if trace.type == 'scatter' and (trace.mode == 'lines' or trace.mode is None):
                trace.mode = 'lines+markers+text'
                trace.texttemplate = '%{y:.0f}'
                trace.textposition = 'top center'
                trace.marker.size = 8
    
    elif graph_type == "bar":
        fig.update_traces(
            texttemplate="%{y:.0f}",
            textposition="outside",
            selector=dict(type="bar")
        )
    elif graph_type == "scatter":
        fig.update_traces(
            mode="markers+text",
            texttemplate="%{y:.0f}",
            textposition="top center",
            marker=dict(size=8),
            selector=dict(type="scatter")
        )

    # 2. Übriges Design (Dark-Mode, Fonts...)
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=50, l=10, r=10, b=10),
        font=dict(family="sans serif", size=12, color="#E2E8F0"),
        hoverlabel=dict(
            bgcolor="#1E293B",
            font_size=13,
            font_family="sans serif"
        )
    )
    # Refine grid visibility for sleeker look
    fig.update_xaxes(showgrid=False, tickformat="%d.%m.")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.05)")
    return fig
