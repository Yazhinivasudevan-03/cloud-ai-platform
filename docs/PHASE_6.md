# Phase 6 — Resource Optimization & Cost Prediction

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 6 of ~10
Status: **Complete and verified**

---

## 1. Overview

Phase 6 adds the platform's resource optimization engine and cost forecasting
capability, closing out the "AI-Driven Predictive Resource Optimization"
half of the project's name. A rule-based recommendation engine analyzes
sustained (not momentary) CPU/memory utilization per deployment and produces
all eight recommendation types named in the original spec (increase/reduce
CPU, increase/reduce memory, increase/reduce pods, scale deployment, optimize
cost), while a lightweight cost forecaster projects next month's spend from
`cloud_costs` billing history. Both reuse the exact idempotent
create/dismiss lifecycle pattern and shared-scheduler architecture
established in Phase 5, rather than inventing a new one.

## 2. Objectives Completed

- [x] Schema migration: `memory_limit_mb` added to `deployments` (nullable) - the one genuinely new piece of data needed, since `cpu_usage_percent` is already a 0-100 percentage but `memory_usage_mb` is an absolute value with no configured capacity to compare against
- [x] Rule engine producing all 8 named recommendation types, each under clearly distinct, non-overlapping trigger conditions
- [x] `scale_deployment` computed via the real Kubernetes HPA formula (`ceil(currentReplicas × currentUtilization / targetUtilization)`)
- [x] `optimize_cost` bundles a real estimated-savings figure when `cloud_costs` history exists for the project, and an honest "no data to estimate from" message when it doesn't
- [x] Idempotent lifecycle: no duplicate pending recommendations while a condition persists; auto-dismissed once the condition clears (same pattern as Phase 5's alerts)
- [x] Cloud cost ingestion + query REST API, and a pure-Python (no new ML dependency) linear-regression monthly cost forecaster with a naive single-period fallback
- [x] Scheduler refactored to a single shared `BackgroundScheduler` instance, with both the Phase 5 alert job and this phase's optimization job registered onto it (was two separate scheduler threads before this refactor)
- [x] 37 new tests (117 total across all phases), all passing against real MySQL
- [x] Full live verification: real sustained-utilization data → real recommendations with correct math, real 3-month cost trend → correct linear-regression forecast, apply lifecycle confirmed

## 3. The Eight Recommendation Types & Their Trigger Conditions

| Type | Condition | Direction |
|---|---|---|
| `increase_pods` | avg CPU ≥ 85% AND replicas < 10 (scaling ceiling) | increase |
| `increase_cpu` | avg CPU ≥ 85% AND replicas ≥ 10 (already scaled out) | increase |
| `reduce_pods` | avg CPU ≤ 15% AND replicas > 1 | decrease |
| `reduce_cpu` | avg CPU ≤ 15% AND replicas == 1 (can't scale in further) | decrease |
| `increase_memory` | memory_limit_mb configured AND avg memory ≥ 85% of limit | increase |
| `reduce_memory` | memory_limit_mb configured AND avg memory ≤ 15% of limit | decrease |
| `scale_deployment` | avg CPU outside a 60%±15% target band AND the HPA formula's target replica count differs from current | either |
| `optimize_cost` | any of the above fired with `direction="decrease"` | - |

**Horizontal before vertical**: a deployment under CPU pressure gets
`increase_pods` while it has headroom under the configurable scaling
ceiling (`OPTIMIZATION_MAX_SCALE_REPLICAS`, default 10), and only falls back
to `increase_cpu` once already scaled out that far - horizontal scaling is
the Kubernetes-native lever, so it's preferred. The inverse applies for low
utilization.

**Why `scale_deployment` can co-occur with `increase_pods`/`reduce_pods`**:
these represent different granularities of the same underlying signal - a
categorical recommendation ("scale out") plus a quantitative one (the exact
target replica count via the HPA formula) - not duplicate noise. This is
disclosed here rather than treated as an oversight.

**Sustained, not momentary**: unlike Phase 5's alert engine (which reacts to
the single most recent data point, appropriate for incident response),
optimization recommendations are computed from the average of the last
`OPTIMIZATION_LOOKBACK_ROWS` (default 24) `resource_usage` rows - a
recommendation to permanently resize a deployment shouldn't be triggered by
one noisy spike. This was directly observed during verification: an isolated
91% CPU data point ingested into a deployment with 21 days of mostly-normal
synthetic history from Phase 4 produced **zero** new recommendations,
because the 24-row rolling average stayed well under the 85% threshold -
correct behavior, not a bug (confirmed by re-testing against a fresh
deployment with 24 consistently high readings, which correctly produced 3
recommendations).

## 4. Cost Forecasting

`cloud_costs` (modelled since Phase 1, unused until now) is aggregated by
calendar month per project. With ≥ 2 months of history, a plain ordinary-
least-squares line is fit over (month index, total cost) and extrapolated
one step forward; with exactly 1 month, the forecast is naively that month's
total (no trend to fit); with 0 months, the API returns
`404 NO_COST_HISTORY` rather than guessing. This is deliberately pure Python
(a manual least-squares fit is about 6 lines) - no numpy/pandas needed for a
single-variable linear regression, and it doesn't touch the ml-models
pipeline (which is reserved for the genuinely model-based Phase 4 work).
Verified live: 3 months of $800/$1000/$1200 (a clean $200/month trend)
correctly forecast $1400 for the next month with `trend_slope_per_month: 200`.

## 5. Folder/File Structure

```
backend/app/
├── optimization/
│   ├── recommendation_engine.py    # pure decision logic, no DB access, fully unit-testable
│   ├── cost_forecaster.py           # pure-Python linear regression over monthly cost aggregates
│   └── scheduler.py                  # registers the optimization job onto the shared scheduler
├── scheduler.py                        # NEW: shared BackgroundScheduler factory (Phase 5's alert
│                                        # scheduler and this phase's optimization scheduler both
│                                        # register jobs onto one instance now, not two)
├── schemas/{optimization_recommendation,cloud_cost}.py
├── repositories/{optimization_recommendation,cloud_cost}_repository.py
├── services/{optimization,cloud_cost}_service.py
├── controllers/{optimization,cloud_cost}_controller.py
└── routers/{optimization,cloud_cost}_router.py

backend/alembic/versions/bec2b8752234_add_memory_limit_mb_to_deployments.py

backend/tests/
├── test_recommendation_engine.py    # pure unit tests, no DB
├── test_cost_forecaster.py            # pure unit tests, no DB
├── test_optimization_service.py        # DB-level lifecycle tests
├── test_optimization_api.py             # REST API tests
└── test_cloud_costs_api.py                # REST API tests
```

## 6. API Endpoints

### `POST /api/v1/optimization/evaluate` (operator/admin)
Runs the recommendation engine now. Response `200`:
```json
{ "deployments_evaluated": 4, "recommendations_created": 3, "recommendations_dismissed": 0 }
```

### `GET /api/v1/deployments/{id}/optimization-recommendations?status=&recommendation_type=&page=&page_size=`
Paginated list. Error: `404 DEPLOYMENT_NOT_FOUND`.

### `GET /api/v1/optimization-recommendations/{id}` / `PATCH .../{id}` (operator/admin for PATCH)
`PATCH` body `{"status": "applied"}` or `{"status": "dismissed"}`. Only `pending` recommendations can be actioned - `409 INVALID_RECOMMENDATION_TRANSITION` otherwise.

### `POST /api/v1/projects/{id}/cloud-costs` (operator/admin)
Request: `{"provider": "aws", "service_name": "EC2", "cost_amount": 1200.00, "currency": "USD", "billing_period_start": "2026-06-01", "billing_period_end": "2026-06-30"}`. Validates `billing_period_end >= billing_period_start`.

### `GET /api/v1/projects/{id}/cloud-costs?provider=&since=&until=&page=&page_size=`
Paginated billing history.

### `GET /api/v1/projects/{id}/cost-forecast`
```json
{ "predicted_next_month_cost": 1400.0, "currency": "USD", "method": "linear_regression",
  "historical_periods_used": 3, "trend_slope_per_month": 200.0 }
```
Error: `404 NO_COST_HISTORY` if no billing entries exist yet.

## 7. Environment Variables Added

| Variable | Default | Purpose |
|---|---|---|
| `OPTIMIZATION_EVALUATION_INTERVAL_MINUTES` | 60 | Scheduler interval (less frequent than alerts - trends, not incidents) |
| `OPTIMIZATION_LOOKBACK_ROWS` | 24 | Rows averaged per deployment per evaluation |
| `OPTIMIZATION_CPU_HIGH_THRESHOLD` / `_LOW_THRESHOLD` | 85 / 15 | CPU utilization tiers |
| `OPTIMIZATION_MEMORY_HIGH_THRESHOLD` / `_LOW_THRESHOLD` | 85 / 15 | Memory utilization tiers (of configured limit) |
| `OPTIMIZATION_TARGET_CPU_PERCENT` / `_BAND` | 60 / 15 | HPA-style scale_deployment target and tolerance band |
| `OPTIMIZATION_MAX_SCALE_REPLICAS` | 10 | Horizontal-vs-vertical scaling decision point |
| `OPTIMIZATION_COST_RIGHTSIZING_SAVINGS_FRACTION` | 0.15 | Assumed savings fraction when estimating `optimize_cost` |

## 8. Verification Results

**Verified live against the running Docker stack, with real data:**
- `alembic revision --autogenerate` detected exactly the one intended schema change (`memory_limit_mb`); applied cleanly
- Both scheduled jobs confirmed registered on the single shared scheduler (`Alert evaluation job registered (every 5 minutes)` + `Optimization evaluation job registered (every 60 minutes)` in logs)
- A single 91%-CPU spike on a deployment with 21 days of mostly-normal history correctly produced **zero** new recommendations (rolling-average smoothing working as designed)
- A fresh deployment with 24 consistently high (91% CPU, 92% of a configured 1000MB memory limit) readings correctly produced exactly 3 recommendations: `increase_pods` ("with 1 replica(s)"), `increase_memory` ("92.0% of the configured 1000MB limit"), and `scale_deployment` ("scale from 1 to 2 replica(s)" - matches `ceil(1 × 91/60) = 2` exactly)
- 3 months of cloud costs with an exact $200/month trend ($800→$1000→$1200) correctly forecast $1400 next month via `linear_regression`, `trend_slope_per_month: 200.0`
- `PATCH .../optimization-recommendations/{id}` correctly transitioned `pending → applied`
- 117/117 backend tests passing (37 new this phase)

## 9. Security Notes

- Write endpoints (`evaluate`, `PATCH` on recommendations, cost ingestion) all require `operator`/`admin`, consistent with platform-wide RBAC.
- Cost figures are read-only computed values (forecast) or operator-supplied ingested values (billing entries) - no external billing API credentials are involved in this phase, so there's no new secret-handling surface.

## 10. Verification Checklist

- [x] Migration autogenerated correctly (single intended column addition) and applied
- [x] All 8 recommendation types confirmed to fire under their designed conditions (11 pure unit tests)
- [x] Idempotency and auto-dismiss lifecycle confirmed (both unit-level and live)
- [x] Cost forecaster: naive fallback, linear regression, negative-cost guard, empty-history error - all confirmed (unit + live)
- [x] Live: sustained-utilization → real recommendations with correct HPA math
- [x] Live: real cost trend → correct forecast
- [x] Live: apply lifecycle transition
- [x] `pytest -v` → **117/117 passing**

## 11. Testing Checklist

- `test_recommendation_engine.py` (11 tests): every recommendation type's exact trigger boundary, HPA formula correctness, target-band no-op case
- `test_cost_forecaster.py` (5 tests): empty history error, naive single-month, multi-entry same-month aggregation, linear regression trend, negative-cost floor
- `test_optimization_service.py` (7 tests): high-CPU/high-memory recommendation creation, idempotency, auto-dismiss on condition clearing, cost-estimate bundling with/without cost data, no-history skip
- `test_optimization_api.py` (8 tests): RBAC, 404s, list/get/apply, invalid-transition rejection
- `test_cloud_costs_api.py` (7 tests): RBAC, validation (end-before-start), ingest+list, forecast (both methods, no-history 404)

## 12. Next Phase Plan (Phase 7)

- Frontend (React + TypeScript + Material UI): the first phase with a UI. Dashboards to visualize everything built so far - resource usage charts, AI predictions/anomalies/failures, alerts, notifications, and now optimization recommendations + cost forecasts - finally giving the six backend phases a face.

**Phase 7 will not start until this Phase 6 report is reviewed and confirmed.**

## 13. References

- Kubernetes Horizontal Pod Autoscaler algorithm: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#algorithm-details
- Ordinary least squares (simple linear regression): https://en.wikipedia.org/wiki/Simple_linear_regression
- Alembic autogenerate: https://alembic.sqlalchemy.org/en/latest/autogenerate.html
