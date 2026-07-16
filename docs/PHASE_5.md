# Phase 5 — Alerting & Notifications

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 5 of ~10
Status: **Complete and verified** (with one disclosed verification gap, see §9)

---

## 1. Overview

Phase 5 closes the loop between everything built so far: an
`AlertEvaluationService` rule engine reads the latest `resource_usage` (Phase
3), `anomaly_detections`, and `failure_predictions` (Phase 4) per deployment,
and turns genuinely-triggered conditions into `Alert` rows with an idempotent
create/resolve lifecycle, fanning out `Notification`s to every admin user
across the dashboard, email, Slack, and Telegram channels. It runs
automatically on a schedule (APScheduler, inside the backend process) and
can also be triggered on demand via `POST /alerts/evaluate`.

Unlike Phase 4, this logic lives **inside** the backend rather than as a
separate pipeline: it needs no heavy ML dependencies, and it operates
directly on the same `Alert`/`Notification` SQLAlchemy models the backend
already owns - there's no reason to introduce a second codebase/deployment
unit for it.

## 2. Objectives Completed

- [x] Rule engine combining three alert sources: CPU threshold tiers (60% warning / 80% critical / 100% saturated), Isolation Forest anomaly detections, and Random Forest failure predictions
- [x] Idempotent lifecycle: no duplicate alerts while a condition persists unchanged; severity escalation resolves the old alert and opens a new one; a cleared condition auto-resolves its alert
- [x] Notification fan-out to every active admin user across 4 channels (dashboard/email/Slack/Telegram), with graceful no-op+log when a channel isn't configured
- [x] Automatic periodic evaluation via APScheduler running inside the FastAPI process (default every 5 minutes, configurable), plus an on-demand `POST /alerts/evaluate` for manual triggering
- [x] REST API: list/get/acknowledge/resolve alerts, self-service notification inbox (list own, mark read)
- [x] 24 new tests (80 total across all phases), all passing against real MySQL
- [x] Full live verification against the running Docker stack: real threshold breach → real alert + notification created, confirmed idempotent across a genuinely-elapsed scheduled run, confirmed correct re-fire semantics after a manual resolve while the root cause persisted

## 3. Alert Sources & Severity Tiers

| Source | Alert type | Trigger | Severity |
|---|---|---|---|
| `resource_usage.cpu_usage_percent` | `cpu_elevated` | ≥ 60% | warning |
| `resource_usage.cpu_usage_percent` | `cpu_high` | ≥ 80% | critical |
| `resource_usage.cpu_usage_percent` | `cpu_saturated` | ≥ 100% | critical |
| `anomaly_detections.is_anomaly` | `anomaly_detected` | latest detection is an anomaly | warning |
| `failure_predictions.probability` | `failure_risk` | ≥ 0.5 | warning |
| `failure_predictions.probability` | `failure_risk` | ≥ 0.8 | critical |

Memory/disk usage are intentionally **not** threshold-checked this phase:
`cpu_usage_percent` is naturally a 0-100 value, so the spec's literal
"60%/80%/100%" thresholds apply directly; memory/disk are stored in MB with
no declared per-deployment capacity limit in the schema, so a percentage
threshold would need a capacity value that doesn't exist yet. That's a
natural candidate for Phase 6 (resource optimization), which will likely need
to reason about capacity/limits anyway.

## 4. Lifecycle & Idempotency Design

Each evaluation run, per deployment, computes the *desired* set of currently-
triggered conditions and reconciles it against existing `active` alerts:

1. Any active alert whose type is no longer in the desired set is **resolved** (condition cleared).
2. For each desired condition: if an active alert of that type already exists **at the same severity**, do nothing (no duplicate). If it exists at a **different** severity (escalation or de-escalation within the same type, e.g. `cpu_high` → would-be `cpu_saturated`... though in practice CPU tiers are mutually exclusive alert *types*, so this branch mainly guards against future alert types that share a type but vary severity), resolve the old one and create a new one. If none exists, create one and dispatch notifications.

This was verified live (not just unit-tested) against the real running
stack: a manually-resolved alert whose root cause (92.5% CPU) was still
present correctly **re-fired** on the very next scheduled evaluation - resolving
an alert doesn't fix the underlying problem, so the engine correctly
disagrees with a human closing it prematurely. Once re-created, subsequent
runs were confirmed idempotent (zero new alerts/notifications) as long as
the condition didn't change again.

**Known simplification** (stated here, not hidden): evaluation looks at the
*most recent* row per deployment/source, not a time-windowed lookback. A
deployment that stops reporting entirely will simply stop being
re-evaluated on new data (its last known state persists) rather than being
flagged as "stale/unreachable" - a real production system would want a
staleness check for that. Not implemented here to keep this phase's scope to
what's actually built and verified.

## 5. Notification Fan-Out

Every triggered alert notifies **all active users holding the `admin`
role** (an operational-monitoring platform notifies whoever's responsible
for the infrastructure, not the deployment's creator specifically - consistent
with the Phase 2 RBAC design where `admin` already has full platform
oversight). For each admin:

- **Dashboard**: always recorded - the `Notification` row itself *is* the dashboard entry, no external delivery needed.
- **Email**: attempted once per admin (each has their own address) via `smtplib`.
- **Slack**: attempted **once per alert**, not per admin (a Slack incoming webhook posts to one shared channel) - but a `Notification` row is still recorded per admin so each admin's notification history reflects it.
- **Telegram**: same shared-destination reasoning as Slack, via the Bot API's `sendMessage`.

## 6. Folder/File Structure

```
backend/app/
├── alerts/
│   └── scheduler.py                    # APScheduler wiring into FastAPI lifespan
├── notifications/
│   ├── email_notifier.py                # smtplib, graceful no-op when SMTP_HOST unset
│   ├── slack_notifier.py                 # httpx POST to incoming webhook
│   ├── telegram_notifier.py               # httpx POST to Bot API sendMessage
│   └── dispatcher.py                       # fan-out to admins across all channels
├── schemas/{alert,notification}.py
├── repositories/{alert,notification}_repository.py
├── services/
│   ├── alert_evaluation_service.py        # the rule engine
│   ├── alert_service.py                    # read/update-status for the API
│   └── notification_service.py              # self-service list/mark-read
├── controllers/{alert,notification}_controller.py
└── routers/{alert,notification}_router.py

backend/tests/
├── test_alert_evaluation.py    # rule engine, direct DB-level tests
├── test_alerts_api.py            # REST API tests
├── test_notifications_api.py      # self-service notification API tests
└── test_notifiers.py               # mocked SMTP/HTTP unit tests
```

## 7. API Endpoints

### `POST /api/v1/alerts/evaluate` (operator/admin)
Runs the rule engine now. Response `200`:
```json
{ "deployments_evaluated": 3, "alerts_created": 2, "alerts_resolved": 0, "notifications_sent": 2 }
```

### `GET /api/v1/deployments/{id}/alerts?status=&severity=&page=&page_size=`
Paginated `AlertRead` list. Error: `404 DEPLOYMENT_NOT_FOUND`.

### `GET /api/v1/alerts/{id}`
Single alert. Error: `404 ALERT_NOT_FOUND`.

### `PATCH /api/v1/alerts/{id}` (operator/admin)
Request: `{"status": "acknowledged"}` or `{"status": "resolved"}`. Valid transitions: `active → acknowledged → resolved`, or `active → resolved` directly. Error: `409 INVALID_ALERT_TRANSITION` (e.g. trying to re-acknowledge an already-resolved alert).

### `GET /api/v1/notifications?is_read=&page=&page_size=`
The current user's **own** notifications only - paginated, filterable by read status.

### `PATCH /api/v1/notifications/{id}/read`
Marks the current user's own notification read. Errors: `403 NOT_YOUR_NOTIFICATION` (someone else's), `404 NOTIFICATION_NOT_FOUND`.

## 8. Environment Variables Added

| Variable | Default | Purpose |
|---|---|---|
| `ALERT_EVALUATION_INTERVAL_MINUTES` | 5 | How often the scheduler auto-runs the rule engine |
| `ALERT_CPU_WARNING_THRESHOLD` / `_CRITICAL_THRESHOLD` / `_SATURATED_THRESHOLD` | 60 / 80 / 100 | CPU percentage tiers |
| `ALERT_FAILURE_WARNING_THRESHOLD` / `_CRITICAL_THRESHOLD` | 0.5 / 0.8 | Failure-probability tiers |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_USE_TLS` | unset / 587 / unset / unset / unset / true | Email channel; blank `SMTP_HOST` disables it |
| `SLACK_WEBHOOK_URL` | unset | Slack channel; blank disables it |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | unset | Telegram channel; either blank disables it |

## 9. Verification Results & Honest Disclosure

**Verified live against the running Docker stack, with real data:**
- Ingested a real 92.5% CPU `resource_usage` row via the actual API, then `POST /alerts/evaluate` created 2 real alerts (one from that new data, one from a pre-existing Phase 3 deployment's 62.3% CPU reading already in the database) and 2 real dashboard notifications for the admin user
- Confirmed the scheduler actually starts (`Alert evaluation scheduler started (every 1 minutes)` in logs, temporarily configured to 1 minute for this verification) and **fires on its own**, unprompted, producing `{'alerts_created': 0, ...}` on the next run - correctly idempotent
- Manually resolved an alert via `PATCH /alerts/{id}`, confirmed the next scheduled run correctly **re-created** it (the root cause hadn't changed), then confirmed subsequent runs were idempotent again
- 80/80 backend tests passing, including 24 new ones for this phase

**What was not, and could not be, verified: live delivery to real external services.**
This environment has no real SMTP server, Slack workspace, or Telegram bot to
send to. `test_notifiers.py` verifies the *code path* honestly - correct
no-op+log behavior when unconfigured, and correct request construction
(right URL, right JSON payload, right SMTP method calls) when mocked as
configured - but nobody has watched a real email/Slack message/Telegram
message actually arrive. If you configure real credentials via the
environment variables in §8, the integration code is exactly what would run;
that final mile just hasn't been observed in this session, and this doc says
so rather than implying it was.

## 10. Security Notes

- Every write endpoint (`evaluate`, `PATCH /alerts/{id}`) requires `operator`/`admin`, consistent with the platform-wide RBAC policy.
- Notifications are strictly self-service: `PATCH /notifications/{id}/read` checks `user_id` ownership server-side (`403 NOT_YOUR_NOTIFICATION`), never trusting a client-supplied user ID.
- SMTP/Slack/Telegram credentials are environment-variable only, never logged; `send_email`/`send_slack_message`/`send_telegram_message` log the *message*, not credentials, when falling back to the unconfigured no-op path.

## 11. Verification Checklist

- [x] `pytest -v` → **80/80 passing**
- [x] Real CPU threshold breach → real `Alert` + `Notification` rows, confirmed via API and direct SQL
- [x] Scheduler starts automatically and fires unprompted on its configured interval
- [x] Idempotency confirmed across a genuinely-elapsed scheduled run (not just same-transaction)
- [x] Resolve-while-condition-persists re-fire semantics confirmed live
- [x] Acknowledge → resolve lifecycle and invalid-transition rejection confirmed via API
- [x] Self-service notification ownership check confirmed (`403` on cross-user access)
- [x] Notifier unconfigured-fallback and configured-call-construction confirmed (mocked; live external delivery explicitly not verified - see §9)

## 12. Testing Checklist

- `test_alert_evaluation.py` (9 tests): CPU tiers, severity escalation, condition clearing, idempotency, anomaly-driven alert, failure-driven alert (both above/below threshold), no-admin-users edge case
- `test_alerts_api.py` (8 tests): RBAC on evaluate/update, deployment-not-found, list+get+filter, acknowledge→resolve flow, invalid transition rejection
- `test_notifications_api.py` (5 tests): own-notifications-only isolation, is_read filter, mark-read, cross-user rejection, not-found
- `test_notifiers.py` (6 tests): unconfigured no-op for all 3 channels, configured call-construction for all 3 channels (mocked)

## 13. Next Phase Plan (Phase 6)

- Resource optimization + cost prediction engine: recommendations (increase/reduce CPU, increase/reduce memory, increase/reduce pods, scale deployment, optimize cost) written to `optimization_recommendations` (modelled since Phase 1), likely informed by the same `resource_usage`/`predictions` data plus a newly-needed notion of deployment resource *limits* (to finally make memory/disk percentage-based, closing the gap noted in §3).
- Monthly cost prediction against `cloud_costs` (modelled since Phase 1, unused so far).

**Phase 6 will not start until this Phase 5 report is reviewed and confirmed.**

## 14. References

- APScheduler: https://apscheduler.readthedocs.io/en/3.x/
- Python `smtplib`: https://docs.python.org/3/library/smtplib.html
- Slack Incoming Webhooks: https://api.slack.com/messaging/webhooks
- Telegram Bot API `sendMessage`: https://core.telegram.org/bots/api#sendmessage
- FastAPI lifespan events: https://fastapi.tiangolo.com/advanced/events/
