"""LSTM architecture and windowing utilities shared by train.py and predict.py."""
import numpy as np

WINDOW = 24  # hours of history used to predict the next hour


def build_model(window: int = WINDOW):
    """A small LSTM regressor: window -> single next-step forecast.

    Kept deliberately small (one LSTM layer, 32 units) since this is a
    single-deployment, single-metric forecaster trained on a few weeks of
    hourly data - a deeper network would just overfit that amount of data.
    """
    from tensorflow import keras
    from tensorflow.keras import layers

    model = keras.Sequential(
        [
            layers.Input(shape=(window, 1)),
            layers.LSTM(32),
            layers.Dense(16, activation="relu"),
            layers.Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    return model


def make_sequences(values: np.ndarray, window: int = WINDOW) -> tuple[np.ndarray, np.ndarray]:
    """Turn a 1D array of scaled values into (X, y) sliding-window pairs."""
    X, y = [], []
    for i in range(len(values) - window):
        X.append(values[i : i + window])
        y.append(values[i + window])
    return np.array(X), np.array(y)
