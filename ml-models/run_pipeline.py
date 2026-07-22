"""Single CLI entrypoint for the ML pipeline: generate demo data, train, predict.

Usage:
    python run_pipeline.py generate-data --deployment-id 1 --pod-id 1 --days 21
    python run_pipeline.py train --deployment-id 1
    python run_pipeline.py predict --deployment-id 1
    python run_pipeline.py all --deployment-id 1 --pod-id 1

`train`/`predict`/`all` run all three models (LSTM on both cpu_usage_percent
and memory_usage_mb, Isolation Forest, Random Forest) for the given deployment.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from isolation_forest import predict as isolation_forest_predict
from isolation_forest import train as isolation_forest_train
from lstm import predict as lstm_predict
from lstm import train as lstm_train
from random_forest import predict as random_forest_predict
from random_forest import train as random_forest_train
from shared.db import get_engine, reflect_tables
from shared.synthetic_data import generate as generate_synthetic_data_rows

LSTM_METRICS = ["cpu_usage_percent", "memory_usage_mb"]


def cmd_generate_data(args: argparse.Namespace) -> None:
    engine = get_engine()
    tables = reflect_tables(engine)
    summary = generate_synthetic_data_rows(
        engine, tables, args.deployment_id, args.pod_id, days=args.days
    )
    print(json.dumps(summary, indent=2, default=str))


def cmd_train(args: argparse.Namespace) -> None:
    engine = get_engine()
    tables = reflect_tables(engine)

    results = {}
    for metric in LSTM_METRICS:
        results[f"lstm_{metric}"] = lstm_train.train(engine, tables, args.deployment_id, metric)
    results["isolation_forest"] = isolation_forest_train.train(engine, tables, args.deployment_id)
    results["random_forest"] = random_forest_train.train(engine, tables, args.deployment_id)

    print(json.dumps(results, indent=2, default=str))


def cmd_predict(args: argparse.Namespace) -> None:
    engine = get_engine()
    tables = reflect_tables(engine)

    results = {}
    for metric in LSTM_METRICS:
        results[f"lstm_{metric}"] = lstm_predict.predict(engine, tables, args.deployment_id, metric)
    results["isolation_forest"] = isolation_forest_predict.predict(
        engine, tables, args.deployment_id, hours=args.hours
    )
    results["random_forest"] = random_forest_predict.predict(engine, tables, args.deployment_id)

    print(json.dumps(results, indent=2, default=str))


def cmd_all(args: argparse.Namespace) -> None:
    cmd_generate_data(args)
    cmd_train(args)
    cmd_predict(args)


def retrain_all(engine, tables, hours: int = 24) -> dict:
    """Re-train (all 3 models) then predict for every deployment that has
    enough resource_usage history, tolerating individual failures - the
    same "don't let one bad deployment abort the whole batch" pattern as
    the backend's AlertEvaluationService.evaluate_all()/CloudSyncService.sync_all().

    This is what makes retraining actually *automatic*: previously
    `run_pipeline.py train`/`predict` only ever ran for one deployment ID a
    human passed on the command line, with nothing to periodically re-run
    it as new resource_usage data accumulates - see
    kubernetes/base/ml-models-cronjob.yaml, now scheduled to call this
    instead of a single hardcoded --deployment-id.
    """
    with engine.connect() as conn:
        deployment_ids = [row[0] for row in conn.execute(select(tables["deployments"].c.id))]

    succeeded: list[int] = []
    failed: list[dict] = []
    for deployment_id in deployment_ids:
        try:
            for metric in LSTM_METRICS:
                lstm_train.train(engine, tables, deployment_id, metric)
                lstm_predict.predict(engine, tables, deployment_id, metric)
            isolation_forest_train.train(engine, tables, deployment_id)
            isolation_forest_predict.predict(engine, tables, deployment_id, hours=hours)
            random_forest_train.train(engine, tables, deployment_id)
            random_forest_predict.predict(engine, tables, deployment_id)
            succeeded.append(deployment_id)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring above
            failed.append({"deployment_id": deployment_id, "error": str(exc)})

    return {"deployments_attempted": len(deployment_ids), "succeeded": succeeded, "failed": failed}


def cmd_retrain_all(args: argparse.Namespace) -> None:
    engine = get_engine()
    tables = reflect_tables(engine)
    summary = retrain_all(engine, tables, hours=args.hours)
    print(json.dumps(summary, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloud AI Platform - ML pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate-data", help="Backfill synthetic resource_usage/incident history"
    )
    generate_parser.add_argument("--deployment-id", type=int, required=True)
    generate_parser.add_argument("--pod-id", type=int, required=True)
    generate_parser.add_argument("--days", type=int, default=21)
    generate_parser.set_defaults(func=cmd_generate_data)

    train_parser = subparsers.add_parser("train", help="Train all three models")
    train_parser.add_argument("--deployment-id", type=int, required=True)
    train_parser.set_defaults(func=cmd_train)

    predict_parser = subparsers.add_parser("predict", help="Run all three models and persist output")
    predict_parser.add_argument("--deployment-id", type=int, required=True)
    predict_parser.add_argument("--hours", type=int, default=24)
    predict_parser.set_defaults(func=cmd_predict)

    all_parser = subparsers.add_parser("all", help="generate-data + train + predict in one go")
    all_parser.add_argument("--deployment-id", type=int, required=True)
    all_parser.add_argument("--pod-id", type=int, required=True)
    all_parser.add_argument("--days", type=int, default=21)
    all_parser.add_argument("--hours", type=int, default=24)
    all_parser.set_defaults(func=cmd_all)

    retrain_all_parser = subparsers.add_parser(
        "retrain-all",
        help="Retrain + predict for every deployment with enough history, tolerating individual failures",
    )
    retrain_all_parser.add_argument("--hours", type=int, default=24)
    retrain_all_parser.set_defaults(func=cmd_retrain_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
