import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from ml.data import add_features


class FakeModel:
    def predict_proba(self, X):
        import numpy as np

        return np.array([[0.7, 0.3]])


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(api_main, "_model", FakeModel())
    monkeypatch.setattr(
        api_main,
        "fetch_forecast",
        lambda ts: {
            "temperature_2m": 10.0,
            "precipitation": 0.0,
            "snowfall": 0.0,
            "wind_speed_10m": 5.0,
        },
    )
    return TestClient(api_main.app)


def test_predict_returns_probability(client):
    r = client.get("/predict", params={"line": "YU", "at": "2026-09-22T08:00"})
    assert r.status_code == 200
    body = r.json()
    assert body["p_delay_5min"] == 0.3 and body["line"] == "YU" and body["at"] == "2026-09-22T08:00:00"


def test_predict_rejects_unknown_line(client):
    assert client.get("/predict", params={"line": "XX", "at": "2026-09-22T08:00"}).status_code == 422


def test_weather_override_is_applied(client):
    r = client.get(
        "/predict",
        params={"line": "BD", "at": "2026-09-22T08:00", "weather": '{"snowfall": 4}'},
    )
    assert r.json()["weather"]["snowfall"] == 4.0


def test_feature_engineering_flags_weekend_and_service_hours():
    df = add_features(
        pd.DataFrame(
            {
                "hour": pd.to_datetime(["2026-09-20T03:00", "2026-09-22T08:00"]),
                "line": ["YU", "BD"],
                "delays": [0, 1],
                "delays_5min": [0, 1],
                "delay_minutes": [0, 7],
            }
        )
    )
    assert list(df["is_weekend"]) == [1, 0]
    assert list(df["is_service_hour"]) == [0, 1]
    assert list(df["any_delay_5min"]) == [0, 1]
