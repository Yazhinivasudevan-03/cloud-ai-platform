# Phase 21 — Disk / Network / Cost Alert Thresholds

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 21 (continuation of the 13-task alerting request - "build the disk/network/cost threshold alerting next")
Status: **Complete**

---

## 1. Overview

Phase 20 built the Notification Settings page and per-account CPU/memory
alert thresholds, deliberately scoping thresholds to CPU and memory only
- the two metrics with real alert-evaluation logic at the time. This
phase closes three more of the ~20 metrics from the original 13-task
request: **disk**, **network**, and **cost** - each with the same real
60/80/90-tier alerting the CPU/memory work established, not placeholder
configuration.

Disk and network needed a new concept first (a configured limit to turn
raw usage into a percentage, same as memory already required). Cost
needed something structurally different: it's the first alert type in
this platform that is genuinely **project-scoped**, not
deployment-scoped, since spend is tracked per-project via `CloudCost`,
not per-deployment.

## 2. What Was Built

### Disk and network alerting (deployment-scoped, same shape as memory)

- **`Deployment.disk_limit_mb` / `Deployment.network_limit_kbps`** (new,
  nullable - migration `41a5c5ca2eac`) - mirrors `memory_limit_mb`
  exactly: alerting is skipped entirely for a deployment without one
  configured, rather than alerting on a raw MB/kbps figure with no
  meaningful ceiling.
- **Network is evaluated as one combined figure**
  (`network_in_kbps + network_out_kbps` against `network_limit_kbps`),
  not separate inbound/outbound alert families - matching how the
  original request named this "Network Usage" as a single metric, not
  two.
- **`AlertEvaluationService._limit_based_condition()`** (refactored) - the
  previous phase's `_memory_condition()` was generalized into a single
  shared 3-tier evaluator parameterized by metric name, reused for
  memory, disk, and network alike (each still gets its own real
  `ALERT_<METRIC>_*_THRESHOLD` settings and `<metric>_elevated`/
  `<metric>_high`/`<metric>_saturated` alert types). Refactored, not
  rewritten: all pre-existing CPU/memory tests still pass unchanged,
  proving the refactor preserved exact prior behavior.
- **`CloudAccountAlertThreshold`** extended with
  `disk_*_threshold`/`network_*_threshold` override columns (migration
  `41a5c5ca2eac`), following the same per-cloud-account override pattern
  CPU/memory already had.

### Cost alerting (project-scoped - a real architectural first for this platform)

- **`Project.monthly_budget` / `cost_warning_threshold` /
  `cost_critical_threshold` / `cost_saturated_threshold`** (new, nullable
  - migration `41a5c5ca2eac`) - live on `Project` itself, not
  `CloudAccountAlertThreshold`: cost is tracked per-project via
  `CloudCost`, and a cloud provider account has no consistent
  relationship to a project's total spend (a project can span multiple
  accounts, or none) - a deliberate, disclosed deviation from the
  CPU/memory/disk/network pattern, not an oversight.
- **`Alert.project_id`** (new, nullable - migration `41a5c5ca2eac`,
  mirrors `deployment_id`'s existing nullability) - without this, a cost
  alert would have nothing to scope itself to; `Alert` now supports
  either a `deployment_id` or a `project_id` per alert (exactly one, in
  practice, enforced by `AlertEvaluationService` rather than a DB
  constraint).
- **`AlertEvaluationService._evaluate_project_cost()`** (new) - a second
  evaluation loop, parallel to the existing per-deployment one, run for
  every `Project` inside the same `evaluate_all()` call. Sums real
  `CloudCost.cost_amount` rows whose `billing_period_start` falls in the
  current calendar month (matching how the real AWS Cost Explorer sync
  from Phase 19 creates one row per service per month), compares against
  `monthly_budget`, and applies the same idempotent create/resolve
  alert lifecycle every deployment-level alert type already has - just
  keyed by `project_id` instead of `deployment_id`.
- **`GET/PUT /projects/{id}/cost-thresholds`** (new) - follows this
  platform's normal Project RBAC (any authenticated user reads,
  operator/admin writes), *not* the ownership-checked pattern
  `CloudProviderAccount` uses, since Projects were never self-service to
  begin with (see `project_router.py`'s own documented policy).

### Frontend

- Deployment creation form (`MicroserviceDetailPage.tsx`) gained Disk
  limit (MB) / Network limit (kbps) fields alongside the existing Memory
  limit field, plus matching table columns.
- `CloudAccountAlertThresholdsCard.tsx` extended with Disk/Network tier
  rows (the component was already written generically enough that this
  was a data-driven addition, not a rewrite).
- **`ProjectCostThresholdsCard.tsx`** (new) - a card on the Project
  detail page's Cloud Costs tab: monthly budget field plus the three
  cost tiers, shown above the existing forecast/billing-history view.

## 3. A Real Concurrency Bug Found (test infrastructure, not the code)

While verifying the new deployment schema changes, a second
`docker compose run ... pytest` was started while the first (full-suite)
run was still executing - both share the same MySQL test database
container. The second run failed with a MySQL `Duplicate entry 'viewer'`
error on the roles-seeding fixture, because both pytest sessions'
session-scoped `_create_test_schema` fixtures raced to `CREATE`/seed the
same schema concurrently. The first run had already completed
successfully (279 passed) by the time this was investigated, confirming
the failure was a real but purely environmental artifact of running two
test sessions against one shared database - not a defect in the new
disk/network/cost code. Documented here rather than silently ignored;
the lesson (never run two `docker compose run pytest` invocations
concurrently against this project's shared test-database container) is
now noted for future sessions.

## 4. Live Verification (not just unit tests)

Rebuilt and restarted the real `cloud-ai-backend`/`cloud-ai-frontend`
containers. Via the real HTTP API against the live dev database:

1. Created a deployment with `disk_limit_mb=1000`, `network_limit_kbps=1000`.
2. Set the linked project's `monthly_budget=1000` and a custom
   `cost_warning_threshold=40` (below the 60% platform default).
3. Posted a real `resource_usage` row (disk 850/1000 = 85%, network
   (400+250)/1000 = 65%) and a real `cloud_costs` billing entry (450 of
   the 1000 budget = 45%).
4. Ran `POST /alerts/evaluate` for real. Result, read directly from the
   `alerts` table:

   | deployment_id | project_id | alert_type | severity | threshold_percent | message |
   |---|---|---|---|---|---|
   | 24 | NULL | `disk_high` | critical | 80 | "Disk usage at 85.0% of the configured limit - above critical threshold" |
   | 24 | NULL | `network_elevated` | warning | 60 | "Network usage at 65.0% of the configured limit - above warning threshold" |
   | NULL | 20 | `cost_elevated` | warning | **40** | "Monthly spend is 450.00 (45.0% of the 1000.00 budget) - above warning threshold" |

   The cost alert's `threshold_percent` is **40**, not the platform
   default of 60 - proof the custom per-project override was genuinely
   read and applied (45% spend would **not** have alerted under the
   60% default). `disk_high`/`network_elevated` are alert types that
   did not exist anywhere in this codebase before this phase, firing
   correctly off real posted data. `project_id=20`/`deployment_id=NULL`
   on the cost alert confirms the project-scoping design works exactly
   as intended - not conflated with any deployment-level alert.

## 5. Verification Summary

- Backend: **279/279 passing** (255 at the end of Phase 20 + 24 new: 18
  in `test_alert_evaluation.py` (disk tiers, network tiers, cost tiers,
  cost sum-across-services, cost resolve-on-clear, custom cost override),
  1 in `test_cloud_account_alert_thresholds_api.py` (disk/network
  override test - the file's existing "platform defaults" test was
  extended with new assertions rather than counted as a new test), 5 in
  `test_project_cost_thresholds_api.py` (new file). `test_alerts_api.py`'s
  existing evaluate-summary test had its exact-key-set assertion updated
  for the new `projects_evaluated` field, not a new test.
- Frontend: 20/20 Vitest passing (unchanged - this phase's frontend work
  was forms/cards, not new component logic requiring new tests beyond
  what `npm run build`'s type-checking already verifies), lint clean,
  build clean.
- Live-verified against the real running stack and real dev database, as
  detailed in section 4 - not simulated.

## 6. Known Limitations (disclosed)

- **`DeploymentDetailPage`'s existing CPU/Memory usage charts were not
  extended to show Disk/Network** - the Overview tab currently renders
  two side-by-side charts (CPU, Memory); adding Disk/Network charts
  there would need restructuring that layout, which was out of scope for
  this phase's ask (the alerting itself, not new dashboard
  visualizations). The underlying data (`disk_usage_mb`,
  `network_in_kbps`/`network_out_kbps`) is already being ingested and
  alerted on; only the chart UI wasn't extended.
- **Cost alerting sums whole-month spend only** - matching how the real
  Cost Explorer sync (Phase 19) writes one row per service per month
  (`billing_period_start` on the 1st). A project billed with a finer
  granularity than monthly wouldn't be summed correctly by this logic
  without further changes.
- **The remaining ~7 metrics from the original 13-task list** (API
  response time, pod restart count, container/node/pod health as
  distinct alert types, service availability, error rate, request
  rate/latency as an alert type, container crash, Kubernetes events)
  still have no real data source or evaluator - consistent with every
  prior phase's disclosure, these were not addressed here and would need
  their own real telemetry source before threshold config for them would
  be meaningful, not dead configuration.
