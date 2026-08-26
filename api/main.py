"""FastAPI service: probability of a 5-minute-plus delay on a subway line at a given hour.

uvicorn api.main:app --port 8000
GET /predict?line=YU&at=2026-09-22T08:00
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from ml.data import FEATURES, LINES, WEATHER_VARS, add_features, fetch_forecast

MODEL_PATH = Path("models/ttc_delay.joblib")
METRICS_PATH = Path("models/metrics.json")

app = FastAPI(title="TTC delay probability", version="1.0")
_model = None


def model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise HTTPException(503, "model not trained yet; run `python -m ml.train`")
        _model = joblib.load(MODEL_PATH)
    return _model


def frame_for(line: str, at: pd.Timestamp, weather: dict[str, float]) -> pd.DataFrame:
    row = {"hour": at.floor("h"), "line": line, "delays": 0, "delays_5min": 0, "delay_minutes": 0, **weather}
    return add_features(pd.DataFrame([row]))[FEATURES]


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": MODEL_PATH.exists()}


@app.get("/model")
def model_info():
    if not METRICS_PATH.exists():
        raise HTTPException(503, "no metrics yet")
    return json.loads(METRICS_PATH.read_text())


@app.get("/predict")
def predict(
    line: str = Query(..., description="YU, BD or SHP"),
    at: datetime = Query(..., description="ISO timestamp, Toronto local time, e.g. 2026-09-22T08:00"),
    weather: str | None = Query(None, description='optional JSON override, e.g. {"snowfall": 2}'),
):
    if line not in LINES:
        raise HTTPException(422, f"line must be one of {LINES}")
    ts = pd.Timestamp(at)
    try:
        w = fetch_forecast(ts)
    except Exception as exc:  # forecast window exceeded or API down: be explicit, don't guess
        raise HTTPException(502, f"weather unavailable for {ts}: {exc}") from exc
    if weather:
        w.update({k: float(v) for k, v in json.loads(weather).items() if k in WEATHER_VARS})
    p = float(model().predict_proba(frame_for(line, ts, w))[0, 1])
    return {"line": line, "at": ts.floor("h").isoformat(), "p_delay_5min": round(p, 3), "weather": w}
