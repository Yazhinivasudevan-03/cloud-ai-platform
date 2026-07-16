"""Integration tests for the ML pipeline, run against a real (throwaway) MySQL schema.

Uses a shorter synthetic history (10 days) than the default (21 days) purely
for test speed - still comfortably above every model's minimum-rows guard.
"""
from lstm import predict as lstm_predict
from lstm import train as lstm_train
from isolation_forest import predict as isolation_forest_predict
from isolation_forest import train as isolation_forest_train
from random_forest import predict as random_forest_predict
from random_forest import train as random_forest_train
from shared.synthetic_data import generate


def test_generate_synthetic_data_produces_expected_row_counts(engine, tables, deployment_and_pod):
    deployment_id, pod_id = deployment_and_pod
    summary = generate(engine, tables, deployment_id, pod_id, days=10, seed=1)

    assert summary["rows_inserted"] == 10 * 24
    assert summary["incidents"] >= 1
    assert summary["restart_events"] >= 1


def test_lstm_train_and_predict_writes_prediction_with_valid_confidence(
    engine, tables, deployment_and_pod
):
    deployment_id, pod_id = deployment_and_pod
    generate(engine, tables, deployment_id, pod_id, days=10, seed=2)

    metadata = lstm_train.train(engine, tables, deployment_id, "cpu_usage_percent")
    assert 0.0 <= metadata["confidence_score"] <= 1.0

    result = lstm_predict.predict(engine, tables, deployment_id, "cpu_usage_percent")
    assert result["metric_type"] == "cpu_usage_percent"
    assert 0.0 <= result["confidence_score"] <= 1.0
    assert isinstance(result["predicted_value"], float)


def test_isolation_forest_flags_injected_anomalies(engine, tables, deployment_and_pod):
    deployment_id, pod_id = deployment_and_pod
    generate(engine, tables, deployment_id, pod_id, days=10, seed=3)

    metadata = isolation_forest_train.train(engine, tables, deployment_id)
    assert metadata["anomalies_in_training_data"] > 0

    result = isolation_forest_predict.predict(engine, tables, deployment_id, hours=24 * 10)
    assert result["rows_scored"] > 0
    assert result["anomalies_flagged"] >= 0


def test_random_forest_train_and_predict_writes_valid_probability(
    engine, tables, deployment_and_pod
):
    deployment_id, pod_id = deployment_and_pod
    generate(engine, tables, deployment_id, pod_id, days=10, seed=4)

    metadata = random_forest_train.train(engine, tables, deployment_id)
    assert 0.0 <= metadata["precision"] <= 1.0
    assert 0.0 <= metadata["recall"] <= 1.0
    assert metadata["positive_labels_total"] > 0

    result = random_forest_predict.predict(engine, tables, deployment_id)
    assert result["failure_type"] == "deployment_failure"
    assert 0.0 <= result["probability"] <= 1.0
