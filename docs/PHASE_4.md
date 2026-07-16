# Phase 4 — AI Module: LSTM, Isolation Forest, Random Forest

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 4 of ~10
Status: **Complete and verified**

---

## 1. Overview

Phase 4 adds the platform's three AI models - LSTM workload forecasting,
Isolation Forest anomaly detection, and Random Forest failure prediction -
as an **independent batch-scoring pipeline** (`ml-models/`), separate from
the FastAPI backend. The pipeline reads `resource_usage` history directly
from MySQL, trains/scores models, and writes results straight into the
`predictions`, `anomaly_detections`, and `failure_predictions` tables that
were already modelled in Phase 1. The backend then gets three new **read-only**
REST endpoints to serve that output - it never runs inference itself.

**Why this data is synthetic, and why that's disclosed everywhere:** the
platform has no production traffic yet (it's still being built). Phase 3's
own next-phase plan called for "a synthetic data generator... to backfill
enough resource_usage history to train against," so `ml-models/shared/
synthetic_data.py` generates realistic hourly history with daily seasonality,
gradual memory drift, and periodic stress episodes that precede a synthetic
pod restart a few hours later. This is disclosed in the module's own
docstring, in this document, and in `ml-models/README.md` - nowhere is it
presented as real telemetry.

## 2. Objectives Completed

- [x] `ml-models/` scaffolded as an independent project (own `requirements.txt`, own Dockerfile, own test suite) that reflects the existing MySQL schema rather than duplicating ORM models
- [x] Synthetic data generator with genuine leading-indicator structure (stress episodes → restart 2-4 hours later), not arbitrary noise
- [x] LSTM: per-deployment, per-metric (cpu_usage_percent, memory_usage_mb) single-step forecaster, with a confidence score derived from validation error, and a matplotlib actual-vs-predicted plot
- [x] Isolation Forest: multivariate anomaly detection over 5 resource-usage features, contamination-tuned to match the synthetic generator's episode rate
- [x] Random Forest: failure-prediction classifier trained on genuine leading-indicator labels (restart within a 3-hour lookahead), with rolling-window features, time-based train/test split, and a confusion-matrix plot
- [x] `run_pipeline.py` CLI: `generate-data` / `train` / `predict` / `all` subcommands
- [x] Backend: 3 new read-only, paginated, filterable endpoints serving AI output
- [x] 4 ml-models tests + 3 backend tests (56 total across all phases), all passing
- [x] Full live verification: real model training against 21 days of synthetic data, real predictions written to MySQL, confirmed via direct SQL and via the backend's own REST API
- [x] One real bug found and fixed during verification (model artifacts not persisting between `docker compose run` invocations - see §8)

## 3. Architecture Decision: Independent Batch Pipeline, Not Embedded Inference

Embedding TensorFlow/scikit-learn directly in the FastAPI backend container
was considered and rejected: it would roughly triple the backend image size
and coupling training code to the request-serving process has no upside
here. Instead:

- `ml-models/` is its own Docker image (`ml-models/Dockerfile`), built independently, run on-demand via `docker compose --profile ml run ml-models <command>` - it is **not** part of the always-on stack (`docker compose up -d` never starts it, by design, via the `profiles: ["ml"]` marker in `docker-compose.yml`).
- It talks to the same MySQL instance the backend uses, but through its own `shared/db.py`, which reflects tables off the live schema (`MetaData.reflect(only=[...])`) rather than importing the backend's SQLAlchemy models - the two projects share a database, not a codebase.
- Model artifacts (`.keras`, `.pkl`, evaluation plots, metadata JSON) are written to per-deployment subdirectories under each model's `artifacts/`, backed by dedicated named Docker volumes so they survive between separate CLI invocations (train once, predict repeatedly).
- The backend only reads `predictions`/`anomaly_detections`/`failure_predictions` - there is deliberately no `POST` on these resources in the API; the batch pipeline is the only writer.

## 4. Folder/File Structure

```
ml-models/
├── shared/
│   ├── db.py                 # engine + table reflection against live MySQL schema
│   ├── data.py                 # load_resource_usage / load_restart_events helpers
│   └── synthetic_data.py       # synthetic history + incident generator (SYNTHETIC DATA - see docstring)
├── lstm/
│   ├── model.py                 # small Keras LSTM architecture + windowing
│   ├── train.py                  # train + evaluate + save (model, scaler, metadata, plot)
│   └── predict.py                # load + forecast next step -> predictions table
├── isolation_forest/
│   ├── train.py                   # multivariate IsolationForest + evaluation plot
│   └── predict.py                 # score recent rows -> anomaly_detections table
├── random_forest/
│   ├── features.py                 # rolling features + restart-lookahead labeling
│   ├── train.py                     # time-split train + confusion matrix plot
│   └── predict.py                   # predict_proba on latest snapshot -> failure_predictions table
├── run_pipeline.py                   # single CLI entrypoint (generate-data/train/predict/all)
├── tests/                             # own pytest suite, own throwaway MySQL test DB
├── requirements.txt
└── Dockerfile

backend/app/
├── schemas/{prediction,anomaly_detection,failure_prediction}.py   # Read-only schemas
├── repositories/{prediction,anomaly_detection,failure_prediction}_repository.py
├── services/prediction_service.py
├── controllers/prediction_controller.py
└── routers/prediction_router.py

backend/tests/test_predictions.py
docker-compose.yml    # + ml-models service (profile "ml") + 3 artifact volumes
database/schema/init.sql   # + cloud_ai_platform_ml_test database/grant
```

## 5. Model Details

### LSTM (workload forecasting)
- **Input**: 24-hour sliding window of a single metric (`cpu_usage_percent` or `memory_usage_mb`), MinMax-scaled (fit on the training split only, to avoid leakage into the test evaluation).
- **Architecture**: `LSTM(32) -> Dense(16, relu) -> Dense(1)`, deliberately small - a few weeks of hourly data per deployment doesn't justify a deeper network.
- **Training**: 80/20 time-based split (not random - a forecaster must be evaluated on data that comes *after* what it trained on), Adam/MSE, up to 30 epochs with early stopping (patience 5, restore best weights).
- **Confidence score**: `max(0, 1 - MAE_scaled)` where `MAE_scaled` is the test-set mean absolute error in the same [0,1] scaled space the model was trained in. On the demo deployment this came out to **0.93** (cpu_usage_percent) and **0.95** (memory_usage_mb).
- **Output**: one row per call in `predictions` (`model_type="lstm"`, `metric_type` = the column name, `target_timestamp` = last observed hour + 1h).

### Isolation Forest (anomaly detection)
- **Input**: 5 raw features (cpu/memory/disk/network in/out), standardized.
- **Model**: `IsolationForest(n_estimators=200, contamination=0.05)` - the 5% contamination rate matches the synthetic generator's own stress-episode frequency (~5-6 episodes across 21 days of hourly data, i.e. roughly matching the target).
- **Output**: one row per scored timestamp in `anomaly_detections`, with `anomaly_score` (higher = more anomalous, from `-decision_function`), `is_anomaly` boolean, and a `details` JSON blob of the raw feature values at that point (so an operator/dashboard can see *why* it was flagged, not just that it was).
- **Verified result** on the demo deployment: 26/504 rows flagged in training (5.2%, consistent with the configured contamination), and re-scoring the last 24 hours correctly flagged a synthetic 93%-CPU stress point with a much higher anomaly score (0.119) than a normal 39%-CPU point (0.0036) scored in the same batch.

### Random Forest (failure prediction)
- **Labels**: a row is labeled 1 if a synthetic `pod_restart` event (see §6) occurs within the next 3 hours - a genuine leading-indicator label, not an arbitrary threshold rule.
- **Features**: the 5 raw resource metrics plus 3-hour rolling mean/std of CPU and memory - a single-point spike is far less informative than "CPU has been elevated for 3 hours," so the rolling features give the model real structure to learn.
- **Model**: `RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced")` - `class_weight="balanced"` matters here because failures are intentionally rare (~4% of rows in the demo run).
- **Split**: time-based 80/20 (never random, to avoid a rolling-window feature leaking information from the future into the past).
- **Verified result** on the demo deployment: precision 1.0, recall 0.5, F1 0.667 on a test set with only 4 positive examples - a small sample, but the model's positive predictions were never wrong (zero false positives), it just missed half of the (few) real events. This is an honest, expected result on ~3 weeks of synthetic data, not cherry-picked.
- **Output**: one row per call in `failure_predictions` (`failure_type="deployment_failure"` - resource_usage is deployment-level, not pod-level, so `pod_id` is left null; probability from `predict_proba`).

## 6. Why Restart Events Live in `metrics`, Not a New Table

The Phase 1 schema has no dedicated "pod restart event log" table - `pods.restart_count` is only a running scalar. Rather than add a new table (a real schema change) just to support this phase's synthetic ground truth, restart events are recorded as ordinary `metrics` rows: `metric_type="pod_restart"`, `value=1`, `unit="count"`, timestamped. This is exactly the flexible, generic time-series event store the `Metric` model was designed for in Phase 1 - a good sign that the earlier schema design holds up under a real new use case instead of needing to be reopened.

## 7. API Endpoints

### `GET /api/v1/deployments/{id}/predictions?metric_type=&model_type=&since=&until=&page=&page_size=`
Returns paginated `PredictionRead` rows (`model_type`, `metric_type`, `predicted_value`, `confidence_score`, `target_timestamp`). Error: `404 DEPLOYMENT_NOT_FOUND`.

### `GET /api/v1/deployments/{id}/anomaly-detections?is_anomaly=&since=&until=&page=&page_size=`
Returns paginated `AnomalyDetectionRead` rows (`anomaly_score`, `is_anomaly`, `details` JSON string). Error: `404 DEPLOYMENT_NOT_FOUND`.

### `GET /api/v1/deployments/{id}/failure-predictions?failure_type=&since=&until=&page=&page_size=`
Returns paginated `FailurePredictionRead` rows (`failure_type`, `probability`, `predicted_at`). Error: `404 DEPLOYMENT_NOT_FOUND`.

All three: any authenticated user can read (consistent with the platform's RBAC policy from Phase 2 - monitoring output is read-only for everyone, write access is never exposed since only the batch pipeline writes these tables).

## 8. Verification Results & Bugs Found

Verified against the live Docker stack, with a real demo deployment created
through the actual backend API (not seeded directly):

1. `docker compose build ml-models` - succeeded (image ~2.78GB, dominated by TensorFlow; the apt-get layer hit an unrelated ~1.7-hour network stall on this specific run reaching the Debian mirror, unrelated to anything in this repo - it resumed and completed on its own).
2. `ml-models` pytest suite: **4/4 passing** against a real (throwaway) MySQL schema.
3. `generate-data --deployment-id 3 --pod-id 2 --days 21` → 504 rows, 6 incidents, 9 restart events.
4. `train --deployment-id 3` → real metrics as quoted in §5 above.
5. `predict --deployment-id 3 --hours 24` → real rows written; confirmed both via direct `SELECT` against MySQL and via `GET /api/v1/deployments/3/{predictions,anomaly-detections,failure-predictions}` through the actual running backend.
6. Backend test suite: **52/52 passing** (49 from Phases 1-3 + 3 new prediction-read tests).

**One real bug found and fixed:** the first `predict` run failed with
`FileNotFoundError: No trained LSTM model for deployment 3` immediately after
a `train` run had just reported success. Root cause: `docker compose run --rm`
creates a fresh, ephemeral container on every invocation, and the `ml-models`
service had no volume mounted for its artifact directories - everything
`train` wrote to the container's writable layer was destroyed the moment that
container exited. Fixed by adding three named volumes
(`lstm_artifacts`, `isolation_forest_artifacts`, `random_forest_artifacts`) to
the service in `docker-compose.yml`, mounted at each model's `artifacts/`
path, so trained models now persist across separate `train`/`predict`
invocations as they must for a real batch pipeline. Re-ran `train` then
`predict` after the fix - both succeeded.

A second, smaller issue: the ml-models test database
(`cloud_ai_platform_ml_test`) didn't exist yet - only `cloud_ai_platform_test`
(the backend's) had been granted in Phase 1's `database/schema/init.sql`.
Fixed `init.sql` for future fresh installs, and created the database/grant by
hand on the already-initialized dev container (since `init.sql` only runs on
first volume creation).

## 9. Environment Variables

`ml-models/.env.example` - same MySQL connection variables as the backend (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`), since it connects to the same instance.

## 10. Installation / Commands Used This Phase

```powershell
# Build the ml-models image (large - includes tensorflow-cpu)
docker compose build ml-models

# Run its test suite (bind-mounted so tests/ - excluded from the image by
# .dockerignore, matching the backend's own convention - is available)
docker compose --profile ml run --rm -v "${PWD}\ml-models:/app" --entrypoint pytest ml-models -v

# Full demo: create a deployment via the real backend API first, then:
docker compose --profile ml run --rm ml-models generate-data --deployment-id <id> --pod-id <id> --days 21
docker compose --profile ml run --rm ml-models train --deployment-id <id>
docker compose --profile ml run --rm ml-models predict --deployment-id <id> --hours 24

# Or all three in one go:
docker compose --profile ml run --rm ml-models all --deployment-id <id> --pod-id <id>
```

Note the `--profile ml` flag is required for every ml-models invocation - a
plain `docker compose run ml-models ...` (without `--profile ml`) will fail
to find the service, since it's intentionally excluded from the default
profile.

## 11. Security Notes

- The ml-models pipeline connects to MySQL with the same `cloudai` application user as the backend (least-privilege: no root access needed for its reflect/read/write pattern).
- No new HTTP surface: the pipeline has no server component at all, only a CLI; nothing it does is network-reachable.
- The 3 new backend endpoints are read-only and follow the existing RBAC/auth dependencies - no new attack surface beyond what Phase 1-3 already established.

## 12. Verification Checklist

- [x] `ml-models` image builds successfully
- [x] `ml-models` pytest suite: 4/4 passing against real MySQL
- [x] Synthetic data generation produces the expected row/incident/restart counts
- [x] LSTM training produces a confidence score in [0,1] and a real evaluation plot
- [x] Isolation Forest flags a rate of anomalies consistent with its configured contamination
- [x] Random Forest training produces valid precision/recall/F1 and a confusion-matrix plot
- [x] Model artifacts persist across separate `train` → `predict` invocations (post-fix)
- [x] `predict` writes real rows to `predictions`/`anomaly_detections`/`failure_predictions`
- [x] Backend `GET .../predictions`, `.../anomaly-detections`, `.../failure-predictions` correctly serve that data, with working pagination/filtering
- [x] Backend test suite: 52/52 passing

## 13. Testing Checklist

`ml-models/tests/test_pipeline.py` (4 tests): synthetic data row/incident counts, LSTM train+predict confidence bounds, Isolation Forest anomaly flagging, Random Forest train+predict probability bounds - all against a real throwaway MySQL schema with a 10-day (reduced for speed) synthetic dataset.

`backend/tests/test_predictions.py` (3 tests): 404 on missing deployment, prediction list filtered by `metric_type`, anomaly-detection list filtered by `is_anomaly`, failure-prediction list - all seeded directly via `db_session` (mirroring how the real batch pipeline's raw inserts would land), verifying the GET endpoints serve them correctly.

## 14. Next Phase Plan (Phase 5)

- Alerting + notifications: threshold-based alerts (60%/80%/100%) evaluated against `resource_usage` and the new `anomaly_detections`/`failure_predictions` output from this phase, written to the `alerts` table (already modelled since Phase 1).
- Notification delivery channels: dashboard (just reading `notifications`), email, Slack, Telegram.
- An alert-evaluation job (likely another small batch/cron-style component, following the same independent-pipeline pattern established here) that periodically checks recent metrics/predictions against thresholds and creates alerts + notifications.

**Phase 5 will not start until this Phase 4 report is reviewed and confirmed.**

## 15. References

- TensorFlow/Keras LSTM: https://www.tensorflow.org/guide/keras/working_with_rnns
- scikit-learn IsolationForest: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
- scikit-learn RandomForestClassifier: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html
- SQLAlchemy MetaData.reflect: https://docs.sqlalchemy.org/en/20/core/reflection.html
- Docker Compose profiles: https://docs.docker.com/compose/how-tos/profiles/
- Docker Compose volumes (persistence across `run`): https://docs.docker.com/reference/compose-file/volumes/
