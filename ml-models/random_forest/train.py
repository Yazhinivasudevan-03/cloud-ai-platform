"""Train a Random Forest failure-prediction classifier for one deployment.

Usage:
    python -m random_forest.train --deployment-id 1
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix, precision_recall_fscore_support

from random_forest.features import build_feature_frame, build_labels, feature_columns
from shared.data import load_resource_usage, load_restart_events
from shared.db import get_engine, reflect_tables

ARTIFACT_ROOT = Path(__file__).parent / "artifacts"


def train(engine, tables, deployment_id: int) -> dict:
    df = load_resource_usage(engine, tables, deployment_id)
    if len(df) < 100:
        raise ValueError(
            f"Not enough history for deployment {deployment_id} to train on "
            f"({len(df)} rows, need at least 100). Run data generation first."
        )
    restart_events = load_restart_events(engine, tables, deployment_id)

    X = build_feature_frame(df).to_numpy(dtype="float64")
    y = build_labels(df, restart_events)

    split_idx = int(len(df) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    model = RandomForestClassifier(
        n_estimators=200, max_depth=8, class_weight="balanced", random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", zero_division=0
    )

    out_dir = ARTIFACT_ROOT / str(deployment_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / "model.pkl")

    metadata = {
        "deployment_id": deployment_id,
        "feature_columns": feature_columns(),
        "training_rows": len(df),
        "positive_labels_total": int(y.sum()),
        "positive_labels_test": int(y_test.sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1_score": float(f1),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
    disp = ConfusionMatrixDisplay(cm, display_labels=["no failure", "failure"])
    disp.plot()
    plt.title(f"Random Forest confusion matrix - deployment {deployment_id}")
    plt.tight_layout()
    plt.savefig(out_dir / "evaluation.png")
    plt.close()

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Random Forest failure model")
    parser.add_argument("--deployment-id", type=int, required=True)
    args = parser.parse_args()

    engine = get_engine()
    tables = reflect_tables(engine)
    metadata = train(engine, tables, args.deployment_id)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
