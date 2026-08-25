"""Train the delay-probability model, evaluate on a time-based holdout, save model + metrics.

    python -m ml.train             # writes models/ttc_delay.joblib and models/metrics.json

The Airflow DAG runs this after dbt_test, so the model retrains every day on the newest data.
Time split (not random): everything before SPLIT trains, everything after tests. Random splits leak
tomorrow's weather regime into today's training and flatter the metrics.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.data import FEATURES, HISTORY_FEATURES, TARGET, build_training_frame

log = logging.getLogger("ml.train")
MODEL_PATH = Path("models/ttc_delay.joblib")
METRICS_PATH = Path("models/metrics.json")


def make_model() -> Pipeline:
    pre = ColumnTransformer(
        [("line", OneHotEncoder(handle_unknown="ignore"), ["line"])],
        remainder="passthrough",
    )
    clf = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        random_state=0,
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def baseline_rate(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    """What a dashboard would show: historical rate for this (line, weekday, hour)."""
    rate = train.groupby(["line", "weekday", "hour_of_day"])[TARGET].mean().rename("p")
    return test.join(rate, on=["line", "weekday", "hour_of_day"])["p"].fillna(train[TARGET].mean())


def evaluate(y, p) -> dict:
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def main() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    df = build_training_frame().dropna(subset=["temperature_2m"])
    split = df["hour"].max() - pd.Timedelta(days=90)  # last 90 days are the holdout
    train, test = df[df["hour"] < split], df[df["hour"] >= split]
    log.info(
        "rows: train=%d test=%d (split at %s); positive rate=%.3f",
        len(train),
        len(test),
        split.date(),
        df[TARGET].mean(),
    )

    model = make_model().fit(train[FEATURES], train[TARGET])
    p_model = model.predict_proba(test[FEATURES])[:, 1]
    p_base = baseline_rate(train, test)

    # Experiment, reported but not served: what if the model also knew the last 1h / 24h of delays on the line?
    informed = make_model().fit(train[FEATURES + HISTORY_FEATURES], train[TARGET])
    p_informed = informed.predict_proba(test[FEATURES + HISTORY_FEATURES])[:, 1]

    metrics = {
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rows_train": int(len(train)),
        "rows_test": int(len(test)),
        "test_from": split.date().isoformat(),
        "positive_rate": round(float(df[TARGET].mean()), 4),
        "model": evaluate(test[TARGET], p_model),
        "baseline_line_weekday_hour": evaluate(test[TARGET], p_base),
        "experiment_with_recent_history": evaluate(test[TARGET], p_informed),
        "features": FEATURES,
    }
    # Retrain on everything before saving, so the served model has the most recent data.
    model = make_model().fit(df[FEATURES], df[TARGET])
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    log.info(
        "model: %s  baseline: %s",
        metrics["model"],
        metrics["baseline_line_weekday_hour"],
    )
    return metrics


if __name__ == "__main__":
    main()
