"""Train a multivariate Isolation Forest over a deployment's resource_usage history.

Usage:
    python -m isolation_forest.train --deployment-id 1
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from shared.data import load_resource_usage
from shared.db import get_engine, reflect_tables

ARTIFACT_ROOT = Path(__file__).parent / "artifacts"
FEATURE_COLUMNS = [
    "cpu_usage_percent",
    "memory_usage_mb",
    "disk_usage_mb",
    "network_in_kbps",
    "network_out_kbps",
]
CONTAMINATION = 0.05  # expected proportion of outliers, matches the synthetic generator's episode rate


def train(engine, tables, deployment_id: int) -> dict:
    df = load_resource_usage(engine, tables, deployment_id)
    if len(df) < 50:
        raise ValueError(
            f"Not enough history for deployment {deployment_id} to train on "
            f"({len(df)} rows, need at least 50). Run data generation first."
        )

    X = df[FEATURE_COLUMNS].to_numpy(dtype="float64")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200, contamination=CONTAMINATION, random_state=42, n_jobs=-1
    )
    model.fit(X_scaled)

    scores = -model.decision_function(X_scaled)  # higher = more anomalous
    is_anomaly = model.predict(X_scaled) == -1

    out_dir = ARTIFACT_ROOT / str(deployment_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / "model.pkl")
    joblib.dump(scaler, out_dir / "scaler.pkl")

    metadata = {
        "deployment_id": deployment_id,
        "feature_columns": FEATURE_COLUMNS,
        "contamination": CONTAMINATION,
        "training_rows": len(df),
        "anomalies_in_training_data": int(is_anomaly.sum()),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    plt.figure(figsize=(10, 4))
    plt.plot(df.index, scores, label="anomaly score")
    plt.scatter(
        df.index[is_anomaly], scores[is_anomaly], color="red", label="flagged anomaly", zorder=3
    )
    plt.title(f"Isolation Forest anomaly scores - deployment {deployment_id}")
    plt.xlabel("recorded_at")
    plt.ylabel("anomaly score (higher = more anomalous)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "evaluation.png")
    plt.close()

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Isolation Forest anomaly model")
    parser.add_argument("--deployment-id", type=int, required=True)
    args = parser.parse_args()

    engine = get_engine()
    tables = reflect_tables(engine)
    metadata = train(engine, tables, args.deployment_id)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
