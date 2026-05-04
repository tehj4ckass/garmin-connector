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


def _add_recovery_metrics(df_days: pd.DataFrame) -> pd.DataFrame:
    if df_days.empty:
        return df_days
    result = df_days.copy()

    # Vectorized calculation of recovery score
    series_parts = []
    if "sleep_score" in result.columns:
        series_parts.append(result["sleep_score"].clip(0, 100) * 0.35)
    if "avg_hrv" in result.columns:
        series_parts.append(result["avg_hrv"].clip(0, 100) * 0.25)
    if "avg_stress" in result.columns:
        series_parts.append((100 - result["avg_stress"]).clip(0, 100) * 0.20)
    if "resting_hr" in result.columns:
        series_parts.append((100 - (result["resting_hr"] - 35) * 2).clip(0, 100) * 0.20)

    if series_parts:
        # Use a temporary DataFrame to sum across columns, skipping NaNs.
        # min_count=1 ensures that if all values in a row are NaN, the sum is NaN.
        result["recovery_score"] = pd.concat(series_parts, axis=1).sum(axis=1, min_count=1).round(2)
    else:
        result["recovery_score"] = None

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


from datetime import datetime, timedelta

def calculate_weekly_trend(df, column, date_col="date", agg="mean"):
    """Calculates percentage change vs previous week."""
    if df.empty or column not in df.columns:
        return 0.0, 0.0
    
    # Sort by date
    df = df.sort_values(date_col)
    max_date = df[date_col].max()
    
    current_week_start = max_date - timedelta(days=6)
    prev_week_start = max_date - timedelta(days=13)
    
    current_week_data = df[df[date_col] >= current_week_start]
    prev_week_data = df[(df[date_col] >= prev_week_start) & (df[date_col] < current_week_start)]
    
    if current_week_data.empty:
        return 0.0, 0.0

    def _get_val(data):
        if data.empty:
            return 0.0
        if agg == "mean":
            return data[column].mean()
        if agg == "sum":
            return data[column].sum()
        if agg == "count":
            return data[column].nunique()
        return 0.0
    
    curr_val = _get_val(current_week_data)
    prev_val = _get_val(prev_week_data)
    
    if prev_val == 0 or pd.isna(prev_val) or pd.isna(curr_val):
        return curr_val, 0.0
        
    delta_pct = ((curr_val - prev_val) / prev_val) * 100
    return curr_val, delta_pct

def render_header(title, subtitle=None):
    """Renders a consistent premium header for all pages."""
    st.markdown(f"""
        <div style="margin-bottom: 2rem;">
            <h1 style="color: #f8fafc; font-weight: 700; margin-bottom: 0.25rem;">{title}</h1>
            {f'<p style="color: #94a3b8; font-size: 1.1rem;">{subtitle}</p>' if subtitle else ''}
        </div>
    """, unsafe_allow_html=True)

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
    
    # 1. Formatting traces
    if graph_type == "line":
        fig.update_traces(
            mode="lines+markers",
            line=dict(width=3, shape='spline'),
            marker=dict(size=8, opacity=0.8),
            connectgaps=True
        )
    elif graph_type == "bar":
        fig.update_traces(
            marker_color="#00ccff",
            marker_line_width=0,
            opacity=0.8
        )
    elif graph_type == "pie":
        fig.update_traces(
            hole=0.4,
            textinfo='percent+label',
            marker=dict(colors=['#00ccff', '#10b981', '#f59e0b', '#6366f1', '#ec4899'])
        )

    # 2. General Layout
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=50, l=10, r=10, b=10),
        font=dict(family="Inter, sans-serif", size=13, color="#E2E8F0"),
        hoverlabel=dict(
            bgcolor="#1E293B",
            font_size=14,
            font_family="Inter, sans-serif",
            bordercolor="rgba(255,255,255,0.1)"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    # Refine axes
    fig.update_xaxes(
        showgrid=False, 
        tickformat="%d.%m.",
        linecolor="rgba(255,255,255,0.1)"
    )
    fig.update_yaxes(
        showgrid=True, 
        gridwidth=1, 
        gridcolor="rgba(255,255,255,0.05)",
        linecolor="rgba(255,255,255,0.1)"
    )
    return fig
