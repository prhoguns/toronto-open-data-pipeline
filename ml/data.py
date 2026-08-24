"""Training data: one row per (subway line, hour) since 2025-01-01, with delay outcome and weather.

Weather comes from Open-Meteo's free archive API (no key), cached to data/weather_hourly.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import psycopg
import requests

from pipeline.config import DbConfig

log = logging.getLogger(__name__)
TORONTO = {"latitude": 43.6532, "longitude": -79.3832, "timezone": "America/Toronto"}
WEATHER_VARS = ["temperature_2m", "precipitation", "snowfall", "wind_speed_10m"]
LINES = ["YU", "BD", "SHP"]
DELAY_THRESHOLD_MIN = 5

GRID_SQL = """
with bounds as (
    select min(delay_date) as d0, max(delay_date) as d1 from marts.fct_ttc_delays
),
hours as (
    select generate_series(d0::timestamp, d1::timestamp + interval '23 hours', interval '1 hour') as hour from bounds
),
grid as (
    select h.hour, l.line_group from hours h cross join unnest(array['YU','BD','SHP']) as l(line_group)
),
delays as (
    select line_group, date_trunc('hour', delay_at) as hour,
           count(*) as delays,
           count(*) filter (where delay_minutes >= %(threshold)s) as delays_5min,
           sum(delay_minutes) as delay_minutes
    from marts.fct_ttc_delays
    where line_group in ('YU','BD','SHP')
    group by 1, 2
)
select g.hour, g.line_group as line,
       coalesce(d.delays, 0) as delays,
       coalesce(d.delays_5min, 0) as delays_5min,
       coalesce(d.delay_minutes, 0) as delay_minutes
from grid g left join delays d using (hour, line_group)
order by g.hour, g.line_group
"""


def load_grid(db: DbConfig | None = None) -> pd.DataFrame:
    with psycopg.connect((db or DbConfig()).dsn) as conn:
        df = pd.read_sql(GRID_SQL, conn, params={"threshold": DELAY_THRESHOLD_MIN})  # type: ignore[arg-type]
    df["hour"] = pd.to_datetime(df["hour"])
    return df


def fetch_weather(start: str, end: str, cache: Path = Path("data/weather_hourly.csv")) -> pd.DataFrame:
    if cache.exists():
        w = pd.read_csv(cache, parse_dates=["hour"])
        if w["hour"].min() <= pd.Timestamp(start) and w["hour"].max() >= pd.Timestamp(end):
            return w
    log.info("fetching weather %s..%s from open-meteo", start, end)
    r = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            **TORONTO,
            "start_date": start,
            "end_date": end,
            "hourly": ",".join(WEATHER_VARS),
        },
        timeout=120,
    )
    r.raise_for_status()
    h = r.json()["hourly"]
    w = pd.DataFrame({"hour": pd.to_datetime(h["time"]), **{v: h[v] for v in WEATHER_VARS}})
    cache.parent.mkdir(parents=True, exist_ok=True)
    w.to_csv(cache, index=False)
    return w


def fetch_forecast(at: pd.Timestamp) -> dict[str, float]:
    """Weather for one future (or recent) hour from the forecast API."""
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            **TORONTO,
            "hourly": ",".join(WEATHER_VARS),
            "past_days": 2,
            "forecast_days": 7,
        },
        timeout=30,
    )
    r.raise_for_status()
    h = r.json()["hourly"]
    idx = pd.to_datetime(h["time"]).get_indexer([at.floor("h")])[0]
    if idx < 0:
        raise ValueError(f"{at} outside forecast window")
    return {v: float(h[v][idx]) for v in WEATHER_VARS}


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour_of_day"] = out["hour"].dt.hour
    out["weekday"] = out["hour"].dt.weekday
    out["month"] = out["hour"].dt.month
    out["is_weekend"] = (out["weekday"] >= 5).astype(int)
    out["is_service_hour"] = ((out["hour_of_day"] >= 6) | (out["hour_of_day"] <= 1)).astype(int)
    out["any_delay_5min"] = (out["delays_5min"] > 0).astype(int)
    if "delays" in out and len(out) > 1:
        g = out.sort_values("hour").groupby("line")["delays"]
        out["delays_prev_1h"] = g.shift(1).fillna(0)
        out["delays_prev_24h"] = g.transform(lambda s: s.shift(1).rolling(24, min_periods=1).sum()).fillna(0)
    return out


FEATURES = [
    "line",
    "hour_of_day",
    "weekday",
    "month",
    "is_weekend",
    "is_service_hour",
    *WEATHER_VARS,
]
# Only available when you know what happened in the hours before (i.e. offline, or with a live delay feed).
HISTORY_FEATURES = ["delays_prev_1h", "delays_prev_24h"]
TARGET = "any_delay_5min"


def build_training_frame(db: DbConfig | None = None) -> pd.DataFrame:
    grid = load_grid(db)
    weather = fetch_weather(grid["hour"].min().strftime("%Y-%m-%d"), grid["hour"].max().strftime("%Y-%m-%d"))
    df = grid.merge(weather, on="hour", how="left")
    return add_features(df)
