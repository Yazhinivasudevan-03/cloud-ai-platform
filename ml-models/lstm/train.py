"""Train an LSTM forecaster for one deployment/metric and save the artifacts.

Usage (see also run_pipeline.py):
    python -m lstm.train --deployment-id 1 --metric cpu_usage_percent
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.preprocessing import MinMaxScaler

from lstm.model import WINDOW, build_model, make_sequences
from shared.data import load_resource_usage
from shared.db import get_engine, reflect_tables

ARTIFACT_ROOT = Path(__file__).parent / "artifacts"


def train(engine, tables, deployment_id: int, metric_column: str, window: int = WINDOW) -> dict:
    df = load_resource_usage(engine, tables, deployment_id)
    if len(df) < window * 3:
        raise ValueError(
            f"Not enough history for deployment {deployment_id} to train on "
            f"({len(df)} rows, need at least {window * 3}). Run data generation first."
        )

    series = df[metric_column].to_numpy(dtype="float32").reshape(-1, 1)

    split_idx = int(len(series) * 0.8)
    train_series, test_series = series[:split_idx], series[split_idx:]

    scaler = MinMaxScaler()
    train_scaled = scaler.fit_transform(train_series)
    test_scaled = scaler.transform(test_series)

    X_train, y_train = make_sequences(train_scaled.flatten(), window)
    X_test, y_test = make_sequences(test_scaled.flatten(), window)
    X_train = X_train.reshape(-1, window, 1)
    X_test = X_test.reshape(-1, window, 1)

    from tensorflow import keras

    model = build_model(window)
    early_stop = keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=5, restore_best_weights=True
    )
    model.fit(
        X_train,
        y_train,
        validation_data=(X_test, y_test),
        epochs=30,
        batch_size=16,
        callbacks=[early_stop],
        verbose=0,
    )

    predictions_scaled = model.predict(X_test, verbose=0).flatten()
    mae_scaled = float(np.mean(np.abs(predictions_scaled - y_test)))
    confidence_score = max(0.0, min(1.0, 1.0 - mae_scaled))

    predictions_actual = scaler.inverse_transform(predictions_scaled.reshape(-1, 1)).flatten()
    actual = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()
    mae_actual = float(np.mean(np.abs(predictions_actual - actual)))

    out_dir = ARTIFACT_ROOT / str(deployment_id) / metric_column
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save(out_dir / "model.keras")
    joblib.dump(scaler, out_dir / "scaler.pkl")

    metadata = {
        "deployment_id": deployment_id,
        "metric_column": metric_column,
        "window": window,
        "mae_scaled": mae_scaled,
        "mae_actual_units": mae_actual,
        "confidence_score": confidence_score,
        "training_rows": len(df),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    plt.figure(figsize=(10, 4))
    plt.plot(actual, label="actual")
    plt.plot(predictions_actual, label="predicted")
    plt.title(f"LSTM forecast vs actual - deployment {deployment_id} - {metric_column}")
    plt.xlabel("test set hour index")
    plt.ylabel(metric_column)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "evaluation.png")
    plt.close()

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the LSTM forecasting model")
    parser.add_argument("--deployment-id", type=int, required=True)
    parser.add_argument(
        "--metric", default="cpu_usage_percent",
        choices=["cpu_usage_percent", "memory_usage_mb"],
    )
    args = parser.parse_args()

    engine = get_engine()
    tables = reflect_tables(engine)
    metadata = train(engine, tables, args.deployment_id, args.metric)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
