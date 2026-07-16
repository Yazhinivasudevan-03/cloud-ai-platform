"""Load a trained LSTM model and write the next-step forecast into `predictions`.

Usage:
    python -m lstm.predict --deployment-id 1 --metric cpu_usage_percent
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
from sqlalchemy import insert

from lstm.model import WINDOW
from shared.data import load_resource_usage
from shared.db import get_engine, reflect_tables

ARTIFACT_ROOT = Path(__file__).parent / "artifacts"


def predict(engine, tables, deployment_id: int, metric_column: str) -> dict:
    out_dir = ARTIFACT_ROOT / str(deployment_id) / metric_column
    model_path = out_dir / "model.keras"
    if not model_path.exists():
        raise FileNotFoundError(
            f"No trained LSTM model for deployment {deployment_id}/{metric_column}. "
            "Run lstm.train first."
        )

    from tensorflow import keras

    model = keras.models.load_model(model_path)
    scaler = joblib.load(out_dir / "scaler.pkl")
    metadata = json.loads((out_dir / "metadata.json").read_text())

    df = load_resource_usage(engine, tables, deployment_id)
    if len(df) < WINDOW:
        raise ValueError(f"Not enough recent history to forecast ({len(df)} rows)")

    window_values = df[metric_column].to_numpy(dtype="float32")[-WINDOW:].reshape(-1, 1)
    scaled = scaler.transform(window_values).flatten().reshape(1, WINDOW, 1)

    predicted_scaled = model.predict(scaled, verbose=0).flatten()[0]
    predicted_value = float(scaler.inverse_transform([[predicted_scaled]])[0][0])

    last_timestamp = df.index[-1]
    target_timestamp = last_timestamp + timedelta(hours=1)

    predictions = tables["predictions"]
    with engine.begin() as conn:
        result = conn.execute(
            insert(predictions).values(
                deployment_id=deployment_id,
                model_type="lstm",
                metric_type=metric_column,
                predicted_value=predicted_value,
                confidence_score=metadata["confidence_score"],
                target_timestamp=target_timestamp,
                generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        prediction_id = result.inserted_primary_key[0]

    return {
        "prediction_id": prediction_id,
        "deployment_id": deployment_id,
        "metric_type": metric_column,
        "predicted_value": predicted_value,
        "confidence_score": metadata["confidence_score"],
        "target_timestamp": target_timestamp.isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LSTM forecasting model")
    parser.add_argument("--deployment-id", type=int, required=True)
    parser.add_argument(
        "--metric", default="cpu_usage_percent",
        choices=["cpu_usage_percent", "memory_usage_mb"],
    )
    args = parser.parse_args()

    engine = get_engine()
    tables = reflect_tables(engine)
    result = predict(engine, tables, args.deployment_id, args.metric)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
