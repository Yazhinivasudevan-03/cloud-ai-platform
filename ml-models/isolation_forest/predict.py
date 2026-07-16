"""Load a trained Isolation Forest and score recent resource_usage rows.

Usage:
    python -m isolation_forest.predict --deployment-id 1 --hours 24
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import joblib
from sqlalchemy import insert

from isolation_forest.train import FEATURE_COLUMNS
from shared.data import load_resource_usage
from shared.db import get_engine, reflect_tables

ARTIFACT_ROOT = Path(__file__).parent / "artifacts"


def predict(engine, tables, deployment_id: int, hours: int = 24) -> dict:
    out_dir = ARTIFACT_ROOT / str(deployment_id)
    model_path = out_dir / "model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(
            f"No trained Isolation Forest model for deployment {deployment_id}. "
            "Run isolation_forest.train first."
        )

    model = joblib.load(model_path)
    scaler = joblib.load(out_dir / "scaler.pkl")

    df = load_resource_usage(engine, tables, deployment_id)
    if df.empty:
        raise ValueError(f"No resource_usage history for deployment {deployment_id}")

    cutoff = df.index[-1] - timedelta(hours=hours)
    recent = df[df.index >= cutoff]

    X = recent[FEATURE_COLUMNS].to_numpy(dtype="float64")
    X_scaled = scaler.transform(X)
    scores = -model.decision_function(X_scaled)
    is_anomaly = model.predict(X_scaled) == -1

    anomaly_detections = tables["anomaly_detections"]
    rows_to_insert = []
    for (timestamp, feature_row), score, flagged in zip(
        recent[FEATURE_COLUMNS].iterrows(), scores, is_anomaly
    ):
        rows_to_insert.append(
            {
                "deployment_id": deployment_id,
                "metric_type": "resource_usage_composite",
                "anomaly_score": float(score),
                "is_anomaly": bool(flagged),
                "detected_at": timestamp,
                "details": json.dumps(feature_row.to_dict()),
            }
        )

    with engine.begin() as conn:
        if rows_to_insert:
            conn.execute(insert(anomaly_detections), rows_to_insert)

    return {
        "deployment_id": deployment_id,
        "rows_scored": len(rows_to_insert),
        "anomalies_flagged": int(sum(is_anomaly)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Isolation Forest anomaly model")
    parser.add_argument("--deployment-id", type=int, required=True)
    parser.add_argument("--hours", type=int, default=24, help="Score the last N hours of data")
    args = parser.parse_args()

    engine = get_engine()
    tables = reflect_tables(engine)
    result = predict(engine, tables, args.deployment_id, args.hours)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
