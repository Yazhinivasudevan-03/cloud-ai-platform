"""Feature engineering and labeling shared by random_forest train/predict.

Label definition: a resource_usage row is labeled 1 ("failure imminent") if a
synthetic pod_restart event (see shared/synthetic_data.py) occurs within the
next LOOKAHEAD_HOURS hours; otherwise 0. This gives the classifier genuine
leading-indicator structure to learn (elevated CPU/memory *before* a restart)
rather than an arbitrary threshold rule.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

LOOKAHEAD_HOURS = 3
ROLLING_WINDOW_HOURS = 3

RAW_FEATURE_COLUMNS = [
    "cpu_usage_percent",
    "memory_usage_mb",
    "disk_usage_mb",
    "network_in_kbps",
    "network_out_kbps",
]


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add rolling mean/std features - a raw spike is far less informative
    than "CPU has been elevated for the last 3 hours", so these give the
    model real predictive power instead of just reacting to single-point noise."""
    df = df.copy()
    for column in ["cpu_usage_percent", "memory_usage_mb"]:
        rolling = df[column].rolling(window=ROLLING_WINDOW_HOURS, min_periods=1)
        df[f"{column}_rolling_mean"] = rolling.mean()
        df[f"{column}_rolling_std"] = rolling.std().fillna(0.0)
    return df


def feature_columns() -> list[str]:
    return RAW_FEATURE_COLUMNS + [
        "cpu_usage_percent_rolling_mean",
        "cpu_usage_percent_rolling_std",
        "memory_usage_mb_rolling_mean",
        "memory_usage_mb_rolling_std",
    ]


def build_labels(df: pd.DataFrame, restart_events: list) -> np.ndarray:
    """Label each row 1 if a restart happens within LOOKAHEAD_HOURS after it."""
    restart_series = pd.Series(sorted(restart_events))
    labels = np.zeros(len(df), dtype=int)
    for i, timestamp in enumerate(df.index):
        window_end = timestamp + timedelta(hours=LOOKAHEAD_HOURS)
        if ((restart_series > timestamp) & (restart_series <= window_end)).any():
            labels[i] = 1
    return labels


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    enriched = add_rolling_features(df)
    return enriched[feature_columns()]
