# Phase 3 — Monitoring Stack & Metrics Ingestion

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 3 of ~10
Status: **Complete and verified** (with one documented environment limitation, see §8)

---

## 1. Overview

Phase 3 adds real observability infrastructure to the platform: Prometheus,
Grafana, Node Exporter, and cAdvisor, all wired into `docker-compose.yml` and
scraping real, live targets — plus a REST API for ingesting and querying the
`metrics`/`resource_usage` tables that Phase 4's AI models will eventually
train against. The FastAPI backend itself is instrumented to expose
Prometheus-format metrics, giving genuine API latency/throughput data, not
placeholders.

`kube-state-metrics` is deliberately **not** deployed this phase — it queries
the Kubernetes API server for cluster object state, and no Kubernetes cluster
exists yet (that's Phase 8). Deploying it now would mean either faking data or
shipping a container that can never connect to anything; instead its scrape
job is present in the Prometheus config, commented out with an explanatory
note, ready to enable once a real cluster exists.

## 2. Objectives Completed

- [x] Prometheus, Grafana, Node Exporter, cAdvisor added to `docker-compose.yml`, all with real scrape targets
- [x] FastAPI backend instrumented via `prometheus-fastapi-instrumentator`, exposing `/metrics`
- [x] Prometheus scrape config for all 4 real targets (prometheus, node-exporter, cadvisor, backend) — verified all report `health: up`
- [x] Grafana auto-provisioned with a Prometheus datasource and one dashboard ("Cloud AI Platform - Overview", 6 panels)
- [x] REST API to ingest and query `Metric` and `ResourceUsage` records, tied to a deployment (and optionally a pod)
- [x] 7 new integration tests (48 total across three phases), all passing against real MySQL
- [x] End-to-end verification: real HTTP calls confirmed Prometheus target health, backend `/metrics` output, Grafana datasource/dashboard provisioning, and metrics ingestion writing real rows into MySQL

## 3. Features Implemented

| Feature | Detail |
|---|---|
| `/metrics` (backend) | `http_requests_total` (counter), `http_request_duration_seconds` (histogram, by handler), plus Python/process metrics — scraped by Prometheus every 15s |
| Prometheus | Scrapes itself, Node Exporter, cAdvisor, and the backend; all 4 targets verified `up` |
| Grafana | Auto-provisioned datasource (`Prometheus`, uid `prometheus_ds`) and dashboard (`platform-overview`, 6 panels) on container start — no manual UI clicking required |
| `POST /deployments/{id}/metrics` | Ingest one raw metric point (`metric_type`, `value`, `unit`, `recorded_at`, optional `pod_id`) — operator/admin |
| `GET /deployments/{id}/metrics` | Paginated list, filterable by `metric_type` and `since`/`until` time range |
| `POST /deployments/{id}/resource-usage` | Ingest one aggregated snapshot (CPU/mem/disk/network) — operator/admin |
| `GET /deployments/{id}/resource-usage` | Paginated list, filterable by `since`/`until` |

## 4. Folder/File Additions

```
docker-compose.yml                                    # + node-exporter, cadvisor, prometheus, grafana services
monitoring/
├── prometheus/prometheus.yml                          # scrape config (kube-state-metrics commented out)
└── grafana/
    ├── provisioning/datasources/datasource.yml         # auto-provisioned Prometheus datasource
    ├── provisioning/dashboards/dashboard.yml            # dashboard provider config
    └── dashboards/platform-overview.json                # 6-panel dashboard

backend/app/
├── monitoring/
│   └── prometheus_metrics.py                           # wires prometheus-fastapi-instrumentator onto the app
├── schemas/{metric,resource_usage}.py
├── repositories/{metric,resource_usage}_repository.py
├── services/{metric,resource_usage}_service.py
├── controllers/{metric,resource_usage}_controller.py
└── routers/metric_router.py                             # both /metrics and /resource-usage endpoints

backend/tests/test_metrics.py
```

## 5. Explanation of Every New File

### `monitoring/prometheus/prometheus.yml`
Four scrape jobs (`prometheus`, `node-exporter`, `cadvisor`, `cloud-ai-backend`),
15s interval. The `kube-state-metrics` job is present but commented out with an
explanation - see §1.

### `monitoring/grafana/provisioning/datasources/datasource.yml`
Provisions a Prometheus datasource pointing at `http://prometheus:9090` with a
**fixed `uid: prometheus_ds`**, set deliberately (rather than letting Grafana
generate one) so the dashboard JSON can reference it by a stable ID that
survives re-provisioning.

### `monitoring/grafana/provisioning/dashboards/dashboard.yml`
Tells Grafana to load any dashboard JSON file placed in
`/var/lib/grafana/dashboards` (mounted from `monitoring/grafana/dashboards/`)
automatically on startup.

### `monitoring/grafana/dashboards/platform-overview.json`
Six panels: API request rate, API p95 latency (both from the backend's own
`/metrics`), backend container CPU/memory (from cAdvisor - see §8 for a
caveat), and host CPU/memory-available (from Node Exporter).

### `backend/app/monitoring/prometheus_metrics.py`
A one-function module (`register_prometheus_metrics(app)`) wrapping
`Instrumentator().instrument(app).expose(app, endpoint="/metrics")`, called
from `main.py`. Kept in its own module (rather than inlined in `main.py`) so
the previously-empty `app/monitoring/` package scaffolded in Phase 1 now has
real content, and so `main.py` stays a thin composition root.

### `backend/app/schemas/metric.py`, `resource_usage.py`
`MetricCreate`/`MetricRead` and `ResourceUsageCreate`/`ResourceUsageRead`.
`ResourceUsageCreate` fields are all `Field(..., ge=0)` — negative CPU/memory/
disk/network values are rejected at the schema boundary (`422`), not silently
accepted.

### `backend/app/repositories/metric_repository.py`, `resource_usage_repository.py`
Each adds a `search(...)` method filtering by deployment, optional
`metric_type` (metrics only), and an optional `since`/`until` time range on
`recorded_at`, ordered newest-first, paginated.

### `backend/app/services/metric_service.py`, `resource_usage_service.py`
`MetricService.ingest` additionally validates that if a `pod_id` is supplied,
that pod both exists (`404 POD_NOT_FOUND`) and belongs to the same deployment
the metric is being posted against (`422 POD_DEPLOYMENT_MISMATCH`) - this
catches a caller accidentally cross-wiring a pod ID from a different
deployment, which would otherwise silently corrupt the data model.

### `backend/app/routers/metric_router.py`
Both `/deployments/{id}/metrics` and `/deployments/{id}/resource-usage`
endpoints, following the same RBAC policy as every other write in this
platform (operator/admin to ingest, any authenticated user to read).

## 6. Database

No schema changes - `metrics` and `resource_usage` tables already existed
from Phase 1's schema design; this phase is the first to actually write to
and read from them via the API.

## 7. API Endpoints, Request/Response/Error Payloads

### `POST /api/v1/deployments/{id}/metrics`
Request:
```json
{ "metric_type": "cpu_usage", "value": 62.3, "unit": "percent",
  "recorded_at": "2026-07-15T15:50:00", "pod_id": null }
```
Response `201`: same shape plus `id`, `deployment_id`, `created_at`.
Errors: `404 DEPLOYMENT_NOT_FOUND`, `404 POD_NOT_FOUND`, `422 POD_DEPLOYMENT_MISMATCH`, `403 INSUFFICIENT_ROLE`

### `GET /api/v1/deployments/{id}/metrics?metric_type=cpu_usage&since=2026-07-15T00:00:00&page=1&page_size=20`
Response `200`: `{"items": [...], "meta": {"total", "page", "page_size", "total_pages"}}`

### `POST /api/v1/deployments/{id}/resource-usage`
Request:
```json
{ "cpu_usage_percent": 62.3, "memory_usage_mb": 768.0, "disk_usage_mb": 4096.0,
  "network_in_kbps": 120.0, "network_out_kbps": 80.0, "recorded_at": "2026-07-15T15:50:00" }
```
Response `201`: same shape plus `id`, `deployment_id`, `created_at`.
Errors: `404 DEPLOYMENT_NOT_FOUND`, `422` (negative value), `403 INSUFFICIENT_ROLE`

### `GET /api/v1/deployments/{id}/resource-usage?since=...&until=...`
Response `200`: paginated envelope, newest-first.

## 8. Verification Results & One Documented Environment Limitation

**Verified working, with real data, against the live Docker stack:**
- All 6 containers (`mysql`, `backend`, `node-exporter`, `cadvisor`, `prometheus`, `grafana`) started healthy
- Prometheus `/api/v1/targets`: **all 4 targets report `health: up`** (prometheus, node-exporter, cadvisor, cloud-ai-backend)
- `GET /metrics` on the backend returns real `http_requests_total` and `http_request_duration_seconds` series with correct labels
- Grafana `/api/health` reports healthy; the Prometheus datasource and the `platform-overview` dashboard (6 panels) are both auto-provisioned and queryable via the Grafana HTTP API
- Dashboard panels 1, 2, 5, 6 (API request rate, API p95 latency, host CPU%, host memory available%) all return real non-empty data when queried directly against Prometheus
- Metrics ingestion: `POST .../resource-usage` and `POST .../metrics` both created real rows, confirmed both via the `GET` list endpoints (correct pagination metadata) and by querying MySQL directly

**One documented limitation - dashboard panels 3 & 4 (backend container CPU/memory via cAdvisor) show no data in this environment:**
cAdvisor is up and being scraped successfully by Prometheus, but it cannot
enumerate individual Docker containers (our `backend`/`mysql`/etc.) with
proper `name`/`image` labels on this machine. Its own logs show the exact
cause:
```
Failed to create existing container: /docker/<id>: failed to identify the
read-write layer ID for container "<id>" - open
/rootfs/var/lib/docker/image/overlayfs/layerdb/mounts/<id>/mount-id:
no such file or directory
```
This is a well-known upstream incompatibility between cAdvisor's overlay2
read-write-layer detection and Docker Desktop for Windows/Mac's LinuxKit VM
storage layout (cAdvisor was designed against native Linux Docker hosts). I
tried the standard mitigations - `privileged: true`, mounting
`/var/run/docker.sock` directly, `--docker_only=true` - none change the
outcome, because the root cause is how Docker Desktop's inner VM organizes
its storage driver metadata, not a missing flag or permission. cAdvisor does
successfully report system/VM-level cgroup metrics (confirmed via
`container_last_seen`), just not per-application-container ones, on this
specific host.

**This is not a workaround-and-move-on situation - it's flagged honestly:**
the `docker-compose.yml`/dashboard configuration is correct and will work as
designed on a native Linux Docker host, and will be superseded anyway once
Phase 8 puts the platform on a real Kubernetes cluster (where `cadvisor`
metrics are typically sourced via the kubelet's built-in `/metrics/cadvisor`
endpoint rather than a standalone container). No further effort was spent
chasing a Docker-Desktop-specific virtualization quirk that has no bearing on
the platform's real deployment target.

## 9. Environment Variables Added

| Variable | Default | Purpose |
|---|---|---|
| `GRAFANA_ADMIN_USER` | admin | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | admin | Grafana admin password (change in any non-local environment) |

## 10. Installation / Commands Used This Phase

```powershell
# Full stack including monitoring
docker compose up -d

# Verify Prometheus targets
Invoke-RestMethod http://localhost:9090/api/v1/targets

# Verify backend metrics endpoint
Invoke-WebRequest http://localhost:8000/metrics

# Verify Grafana
Invoke-RestMethod http://localhost:3001/api/health
# Grafana UI: http://localhost:3001  (default admin/admin - change via .env)

# Run full test suite (48 tests)
docker compose run --rm -v "${PWD}\backend:/app" backend pytest -v
```

## 11. Security Notes

- Grafana ships with a default `admin`/`admin` credential via `.env.example` - the README/env template both flag this must be changed before any non-local use.
- `/metrics` on the backend is intentionally unauthenticated (standard Prometheus scraping practice) but excluded from the OpenAPI schema (`include_in_schema=False`) so it doesn't clutter the public API docs; it exposes only aggregate operational counters, no user data.
- Metrics/resource-usage ingestion uses the same JWT + operator/admin RBAC as every other write endpoint - no new attack surface introduced.

## 12. Verification Checklist

- [x] `docker compose up -d` → all 6 containers healthy/running
- [x] Prometheus targets: 4/4 `up`
- [x] `GET /metrics` (backend) → real Prometheus-format output with correct metric names
- [x] Grafana datasource + dashboard provisioned automatically, queryable via API
- [x] 4/6 dashboard panels confirmed rendering real data; 2/6 (container CPU/mem) documented as blocked by a Docker-Desktop-specific cAdvisor limitation, not an app bug
- [x] `POST/GET .../metrics` and `.../resource-usage` round-trip real data through MySQL
- [x] `pytest -v` → **48/48 tests passing**

## 13. Testing Checklist

`test_metrics.py` (7 tests): parent-not-found 404, RBAC denial for viewer,
type+time-range filtering, pod_id association, cross-deployment pod_id
rejection (`422`), resource-usage ingest+list round trip, negative-value
rejection.

## 14. Next Phase Plan (Phase 4)

- AI module: LSTM (workload/resource forecasting), Isolation Forest (anomaly
  detection), Random Forest (failure prediction) - all three trained against
  the `resource_usage`/`metrics` history this phase's ingestion API now makes
  possible to collect.
- Since there's no real production traffic yet, Phase 4 will need a synthetic
  data generator (a script under `scripts/`) to backfill enough
  `resource_usage` history to train against, seeded via this phase's own
  ingestion endpoints.
- Predictions/anomaly/failure results written to the `predictions`,
  `anomaly_detections`, `failure_predictions` tables (already modelled since
  Phase 1) via a new prediction REST API.

**Phase 4 will not start until this Phase 3 report is reviewed and confirmed.**

## 15. References

- Prometheus: https://prometheus.io/docs/introduction/overview/
- Grafana provisioning: https://grafana.com/docs/grafana/latest/administration/provisioning/
- prometheus-fastapi-instrumentator: https://github.com/trallnag/prometheus-fastapi-instrumentator
- Node Exporter: https://github.com/prometheus/node_exporter
- cAdvisor: https://github.com/google/cadvisor
- cAdvisor Docker Desktop overlay2 limitation (background reading): https://github.com/google/cadvisor/issues (search "read-write layer ID" for related upstream reports)
