"""Load a trained Random Forest model and write a failure probability.

Usage:
    python -m random_forest.predict --deployment-id 1
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sqlalchemy import insert

from random_forest.features import build_feature_frame
from shared.data import load_resource_usage
from shared.db import get_engine, reflect_tables

ARTIFACT_ROOT = Path(__file__).parent / "artifacts"


def predict(engine, tables, deployment_id: int) -> dict:
    out_dir = ARTIFACT_ROOT / str(deployment_id)
    model_path = out_dir / "model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(
            f"No trained Random Forest model for deployment {deployment_id}. "
            "Run random_forest.train first."
        )

    model = joblib.load(model_path)
    df = load_resource_usage(engine, tables, deployment_id)
    if df.empty:
        raise ValueError(f"No resource_usage history for deployment {deployment_id}")

    features = build_feature_frame(df)
    latest_features = features.iloc[[-1]].to_numpy(dtype="float64")
    probability = float(model.predict_proba(latest_features)[0][1])

    failure_predictions = tables["failure_predictions"]
    with engine.begin() as conn:
        result = conn.execute(
            insert(failure_predictions).values(
                deployment_id=deployment_id,
                pod_id=None,
                failure_type="deployment_failure",
                probability=probability,
                predicted_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        failure_prediction_id = result.inserted_primary_key[0]

    return {
        "failure_prediction_id": failure_prediction_id,
        "deployment_id": deployment_id,
        "failure_type": "deployment_failure",
        "probability": probability,
        "based_on_data_as_of": df.index[-1].isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Random Forest failure model")
    parser.add_argument("--deployment-id", type=int, required=True)
    args = parser.parse_args()

    engine = get_engine()
    tables = reflect_tables(engine)
    result = predict(engine, tables, args.deployment_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
