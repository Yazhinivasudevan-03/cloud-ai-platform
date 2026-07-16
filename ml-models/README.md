# ML Models

Implemented in Phase 4 — see [`docs/PHASE_4.md`](../docs/PHASE_4.md) for full detail.

An independent batch-scoring pipeline (own `requirements.txt`, own Docker
image, own test suite) - **not** part of the always-on stack. It reflects the
backend's MySQL schema directly (no duplicated ORM models) and writes
straight into the `predictions`, `anomaly_detections`, and
`failure_predictions` tables; the backend only reads them back via read-only
REST endpoints.

- `shared/db.py`, `shared/data.py` - MySQL connection + table reflection + data loading
- `shared/synthetic_data.py` - **synthetic** demo data generator (no production traffic exists yet); daily seasonality + injected stress episodes that precede a synthetic pod restart, so models have genuine signal to learn from
- `lstm/` - per-deployment, per-metric next-step forecaster (Keras LSTM)
- `isolation_forest/` - multivariate anomaly detection over resource-usage features
- `random_forest/` - failure-prediction classifier, labeled by proximity to a synthetic restart event
- `run_pipeline.py` - CLI: `generate-data` / `train` / `predict` / `all`

## Usage

```powershell
docker compose build ml-models
docker compose --profile ml run --rm ml-models generate-data --deployment-id <id> --pod-id <id> --days 21
docker compose --profile ml run --rm ml-models train --deployment-id <id>
docker compose --profile ml run --rm ml-models predict --deployment-id <id>
```

`--profile ml` is required — this service is intentionally excluded from
`docker compose up -d`. Model artifacts persist across separate invocations
via named Docker volumes (`lstm_artifacts`, `isolation_forest_artifacts`,
`random_forest_artifacts`).
