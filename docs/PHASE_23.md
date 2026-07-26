# Phase 23 — Back Buttons, Notification Bell, Personal Notification Settings, and 9 New Real Alert Evaluators

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 23 (explicit extend-only request: back buttons everywhere, a real Notification Bell, per-user
notification settings with per-category/tier preferences, and - after a follow-up instruction to never
disable or fake any alert category - real evaluators for every one of the platform's 15 alert categories)
Status: **Complete**

---

## 1. Overview

This phase had three parts, of increasing size:

1. **Back buttons everywhere** - a single `BackButton` component wired into the shared
   `PageHeader`, covering every page that already uses it (13 of the app's pages) in one change.
2. **A real Notification Bell + personal notification settings** - severity-broken-down unread
   counts, mark-read/clear/view-details per item, a "View all" link, and a much larger personal
   settings page (full name, secondary email, country code, Telegram username, notification
   language, and a full per-category/tier preference table).
3. **Real alert evaluators for every category the request named**, after an explicit follow-up
   instruction that no category should be disabled, hidden, or trimmed just because it lacked a
   real evaluator - real data only, never fabricated. Before this phase, only CPU/Memory/Disk/
   Network/Cloud Cost/Anomaly-Detection/Failure-Prediction actually produced alerts. This phase
   adds real, non-fabricated evaluators for the remaining 9 named categories: **Cloud Usage,
   Storage, Pod Restart, Resource Optimization, Security, API Latency, Error Rate, Node Failure,
   and Container Failure** - the last two required this platform's first-ever live connection to a
   Kubernetes API server.

Every evaluator here is built entirely from data this platform already collects or an
already-running service it already operates - no random values, no dummy JSON, no mock APIs. Where
that wasn't possible without genuinely new infrastructure (a live Kubernetes cluster), the new
infrastructure is a thin integration module following this project's existing `app/integrations/`
pattern (already used for AWS Cost Explorer and CloudWatch), not a rewrite of anything.

## 2. Back Buttons (Feature 1)

- **`BackButton.tsx`** (new) - `useNavigate(-1)`, i.e. pops the browser's own history stack rather
  than navigating to a fixed route. This is what makes "preserve filters/search/pagination/selected
  cloud account/dashboard state" free: going back restores the exact previous URL and whatever
  component state React Query/local state had for it, with zero extra plumbing.
- Wired into **`PageHeader.tsx`** (shown by default, `hideBackButton` escape hatch for future use) -
  13 of the app's pages already use `PageHeader` (Dashboard, Cloud Accounts, Cloud Account Detail,
  Projects, Project Detail, Microservice Detail, Deployment Detail, Alerts, Optimization,
  Notifications, Notification Settings, Settings, Users), so this one change covers effectively
  every page named in the request - Cloud Usage/Threshold Configuration/Timezone Settings/AI
  Prediction/Anomaly Detection/Failure Prediction/Resource Optimization/Alert History all live as
  tabs or sections *within* Deployment Detail or Cloud Account Detail, both of which now have the
  button once, at the top, covering every tab under them.

## 3. Notification Bell + Personal Notification Settings (Features 2 & 3)

### Database (additive only)

- **`notification_settings`** gained `secondary_email`, `country_code`, `telegram_username`,
  `notification_language` (default `"en"`), and `alert_preferences` (a JSON blob) - migration
  `b08de8ac6a0f`. Primary email/phone are **not** duplicated here - they stay on `User` (reused via
  the existing `PATCH /auth/me`), consistent with this table's original Phase 20 design note that
  email/SMS reuse `User.email`/`User.phone_number` directly. `country_code` is display-only
  metadata (lets the form show country code and local number as two fields); the actual SMS-send
  path is unchanged and still uses the single E.164 `User.phone_number`.
- **`alerts.user_id`** (new nullable FK, migration `3eca2a257121`) - Security alerts (below) are
  per-user, not per-deployment/project, mirroring exactly how `Alert.project_id` was added in
  Phase 21 for the same "this alert type needs a new scope" reason.
- **`cloud_account_alert_thresholds`** gained `cloud_usage_*`/`pod_restart_*` override columns
  (migration `b08de8ac6a0f`) - the two new categories that are genuinely per-cloud-account/per-
  deployment scoped, using the exact same override mechanism CPU/Memory/Disk/Network already have.

### `app/notifications/alert_preferences.py` (new)

Defines the 15 categories (11 tiered - warning/critical/saturated, i.e. the 60/80/90% pattern; 4
simple on/off), parses an `Alert.alert_type` string into `(category, tier)`, and gates whether a
user wants an out-of-band notification for it. Missing/unset preferences default to **fully
enabled** - the core backward-compatibility guarantee: a user who never touches this page keeps
today's always-on behavior exactly as before. Gating gates only the outbound email/SMS/Telegram/
Slack/Teams channels; the in-app dashboard/Notification Bell feed is **never** suppressed by it -
the same precedent Do Not Disturb already established in `dispatcher.py`.

### Notification Bell + history + settings (frontend)

- **`NotificationBell.tsx`** (rewritten) - severity-broken-down unread counts (via the new
  `GET /notifications/summary`), enriched dropdown items (time, provider/region/resource, severity
  chip, message), per-item Mark-as-read/Clear buttons, a "View Details" click-through, and a "View
  all notifications" button.
- **`NotificationsPage.tsx`** (history) - added Severity/Cloud-Region-Resource columns and a Clear
  action per row.
- **`NotificationSettingsPage.tsx`** - added Full Name (wired to the existing `PATCH /auth/me`),
  Secondary Email, Country Code + Phone (split), Telegram Username, Notification Language, a
  data-driven Alert Type Preferences table (15 rows, Enabled + 60/80/90% columns - blank for the 4
  simple categories), and a Cancel button. `SettingsPage.tsx` (the de facto User Profile page)
  gained a link to Notification Settings and had its stale "profile editing isn't available yet"
  note corrected (it's been available via `PATCH /auth/me` since Phase 19; this page just never
  exposed a form for it).

### Backend: `Notification` model/schema enrichment + new endpoints

- `Notification` gained computed `severity`/`alert_type`/`provider`/`region`/`resource`/
  `alert_time_utc`/`alert_time_local` properties reading straight through to the already-computed
  `Alert` properties (Phase 22) - never re-derived, one source of truth.
- **`DELETE /notifications/{id}`** (new, ownership-checked) - "Clear Notification".
- **`GET /notifications/summary`** (new) - unread counts by severity for the bell, counted once per
  alert (the `"dashboard"` channel row) rather than once per delivery channel, so a user with email
  *and* Slack enabled doesn't see their badge count triple-counted.
- `dispatcher.py` gained the alert-preference gate (above) and a secondary-email fan-out (best
  effort, not its own tracked Notification row - a convenience CC, not a second channel).
- `NotificationSettingService.send_test_notification` also attempts the secondary email
  (`NotificationSettingTestResult.secondary_email_sent`).

## 4. The 9 New Real Alert Evaluators

A live feasibility check (see §5) found real, already-available data or an already-running service
for every category - no category was hidden, trimmed, or stubbed:

| Category | Real data source | Scope |
|---|---|---|
| **Cloud Usage** | The highest utilization % across whichever of CPU/memory/disk/network are configured for a deployment - an aggregate of data the other evaluators already compute. Skipped when only CPU is configured (would be a pure duplicate of the CPU alert). | Per-deployment |
| **Storage** | Reuses `disk_usage_mb`/`disk_limit_mb` directly - this platform collects no distinct filesystem/volume metric separate from disk usage, so Storage and Disk observe the same real signal under two alert_type labels, disclosed rather than hidden. | Per-deployment |
| **Pod Restart** | `Pod.restart_count`, collected since Phase 2 via `POST /deployments/{id}/pods` but never alerted on before now. | Per-deployment |
| **Resource Optimization** | Wired directly into `OptimizationService` (Phase 6's real AI-driven recommendation engine) - a real Alert (with real dispatch) now accompanies a deployment's pending recommendation(s), idempotent create/resolve exactly like every other alert type. | Per-deployment |
| **Security** | Real failed-login attempts. `AuditLogMiddleware` has captured every `POST /auth/login` (success or failure) since Phase 18 - see the bug this phase found and fixed in §5. | Per-user (new `Alert.user_id`) |
| **API Latency** | A new `app/integrations/prometheus_client.py` queries this platform's own already-running Prometheus instance (`http_request_duration_seconds_sum`/`_count`, already exposed since Phase 3/18) for average request latency. | Platform-wide |
| **Error Rate** | Same Prometheus instance, `http_requests_total` by status class, for the real 5xx rate. | Platform-wide |
| **Node Failure** | A new `app/integrations/kubernetes_monitor.py` - this platform's first live Kubernetes API connection - reads real node `Ready` conditions. | Platform-wide, cluster-scoped |
| **Container Failure** | Same module - real pod/container status (`CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, etc.), checking **both** main and init containers (see the bug this phase found and fixed in §5). | Platform-wide, cluster-scoped |

API Latency/Error Rate/Node Failure/Container Failure have no natural per-cloud-account or
per-deployment scope (an HTTP request path or a cluster node isn't owned by a specific cloud
account) - a deliberate, disclosed deviation from the CPU/Memory/Disk/Network pattern, the same
reasoning Phase 21 already used for why Cost thresholds live on `Project` instead of
`CloudAccountAlertThreshold`. Kubernetes monitoring is off by default
(`ALERT_KUBERNETES_MONITORING_ENABLED=false`) since most environments running this platform (a
plain `docker compose up`) have no cluster to query - a missing/unreachable cluster is treated as
"skip this evaluator" (`None`), never as "no failures found".

Severity stays **warning/critical only** for every new category (no third "info" tier was added):
introducing a third severity value for only *some* alert types would fragment this platform's
existing, already-tested severity semantics rather than extend them consistently - the 60/80/90%
tiers map onto warning/warning/critical exactly like CPU/Memory/Disk/Network/Cloud Cost already do.

## 5. Real Bugs Found During Live Verification (and fixed)

Live-verifying against the real running stack (not just unit tests with mocked data) caught three
genuine defects that no amount of mocked-data unit testing would have surfaced:

1. **The Prometheus evaluator slowed the entire test suite by ~10x.** `_evaluate_platform_metrics()`
   runs on every `evaluate_all()` call, including the ~300 pre-existing tests that never touch
   Prometheus - each one was making a real, several-second network attempt to an unreachable
   `prometheus:9090` host in the test environment. Fixed by (a) cutting the client's timeout from
   5s to 2s, and (b) forcing `PROMETHEUS_URL` to a closed local port in `conftest.py` so every
   attempt fails instantly (connection refused) instead of waiting out a timeout - the same kind of
   test-environment hygiene fix `OTEL_ENABLED`/`OPTIMIZATION_AUTO_APPLY_ENABLED` already needed.
2. **The Security evaluator could never actually fire.** `AuditLogMiddleware`'s generic audit row
   has `user_id=None` for a login request, since there is no authenticated "current user" for a
   request that hasn't logged in yet - discovered only by registering a real user, deliberately
   failing 5 logins, and finding zero rows the evaluator's own query could match. Fixed by having
   `AuthService.authenticate()` write a second, more precise `AuditLog` row (same
   action/details convention, but with the *targeted* account's real `user_id`) specifically in the
   wrong-password branch, where that account is already known. Live-reverified afterward: 5 real
   failed logins now correctly produce a real `security_high` alert.
3. **Container Failure missed init containers entirely.** This platform's own Helm-deployed backend
   (from Phase 8's one-time cluster verification) has two pods genuinely stuck in
   `Init:CrashLoopBackOff` for over a week - a real, live failure this phase's evaluator should
   have caught immediately. It didn't: `Init:CrashLoopBackOff` means the *init* container is
   crash-looping, which never appears in `pod.status.container_statuses` (only the main
   containers) - only in `pod.status.init_container_statuses`, which the evaluator never checked.
   Fixed by scanning both lists. Live-reverified with a real (temporarily kubeconfig-mounted)
   connection to the actual cluster: correctly reports both pods, container name `migrate`, reason
   `CrashLoopBackOff`, real restart counts (108/113).

## 6. Live Verification (not just unit tests)

Rebuilt and recreated the real `cloud-ai-backend`/`cloud-ai-frontend` containers, plus started
`prometheus`/`cadvisor` (previously not running in this session) so the Prometheus-backed
evaluators had a genuine target. Via the real HTTP API against the live dev database:

1. A real deployment with `memory_limit_mb`/`disk_limit_mb`/`network_limit_kbps` configured,
   posted `disk_usage_mb=920/1000` (92%): **`disk_saturated`**, **`storage_saturated`**, and
   **`cloud_usage_saturated`** (92% - the highest of the four dimensions) all fired correctly from
   the same real data.
2. A real `Pod` with `restart_count=12`: **`pod_restart_saturated`** fired (≥ the default 10).
3. A sustained high-CPU window: a real `OptimizationRecommendation` was created by the existing
   AI-driven engine, and a real **`resource_optimization`** alert accompanied it (disclosed: in
   this particular dev environment `OPTIMIZATION_AUTO_APPLY_ENABLED` happens to be on, so a
   recommendation can resolve itself before staying "pending" long enough to demonstrate live in
   every run - the mechanism itself is deterministically covered by 3 dedicated tests with
   auto-apply forced off, matching this suite's existing convention).
4. `average_latency_ms()`/`error_rate_percent()` queried the real, now-running Prometheus instance
   directly and returned real values (≈3ms average latency, 0.0% error rate) - genuinely below
   every tier, so correctly produced no alert (the tiered logic itself is covered live by the
   Security/disk/storage/cloud_usage results above, plus 4 dedicated unit-mocked tests for the
   exact threshold-crossing case).
5. 5 real failed logins for a throwaway account correctly produced a real **`security_high`** alert
   (after the fix in §5.2) - `"5 failed login attempts in the last 15 minutes - above the critical
   threshold (5)"`.
6. A temporarily kubeconfig-mounted connection to the real Docker Desktop Kubernetes cluster
   correctly found the real, still-ongoing `Init:CrashLoopBackOff` on both `backend` pods in the
   `cloud-ai-platform` namespace (after the fix in §5.3) - genuine cluster state, not fabricated.
7. `PUT /notification-settings` persisted `secondary_email`/`country_code`/`telegram_username`/
   `notification_language`/a partial `alert_preferences` update correctly (one category's tier
   changed, every other category/tier untouched at its default) - confirmed via a follow-up `GET`.
8. `GET /notifications/summary` returned real, non-fabricated zero counts for a fresh operator
   account (dashboard notifications go to admins only, unchanged from Phase 20's fan-out design).

## 7. Verification Summary

- Backend: **389/389 passing** (376 at the end of Phase 22 + new tests across 3 new
  test files - `test_alert_preferences.py`, `test_prometheus_client.py`,
  `test_kubernetes_monitor.py` - plus substantial additions to `test_alert_evaluation.py`,
  `test_optimization_service.py`, `test_optimization_api.py`, `test_notification_dispatcher.py`,
  `test_notification_settings_api.py`, `test_notifications_api.py`, `test_auth.py`, and
  `test_notifiers.py` (§8's reason-code tests)). Also measurably *faster* than before this phase
  (~177-192s vs. ~326s for the same-shaped run earlier in this phase) once the Prometheus-timeout
  bug in §5.1 was fixed.
- Frontend: 20/20 Vitest passing (unchanged count - this phase's frontend work was UI extensions
  verified via `tsc -b` type-checking and the live-verification pass above), `tsc -b` clean.
- Live-verified against the real running stack and real dev database, as detailed in §6 - not
  simulated - including two real bugs (§5) that only live verification against real infrastructure
  could have caught.

## 8. Follow-up: Granular Test-Notification Failure Reasons

After this phase's main commit, a follow-up report came in: "Send Test Notification" showed
`email: not configured / failed, sms: not configured / failed`. Investigation confirmed this is
**correct, honest, disclosed behavior, not a defect** - this environment's `.env` genuinely has no
real SMTP or Twilio credentials at all (checked directly: `SMTP_HOST=`, no `TWILIO_*` variables
present anywhere), so there is nothing to actually deliver through. Real delivery requires the
deployer's own real SMTP/Twilio credentials, which this platform cannot fabricate - the same class
of external-dependency gap disclosed for AWS/Kubernetes access in earlier phases.

What *was* a real, fixable gap: every notifier collapsed every failure mode - unconfigured, a
genuine auth rejection, an unreachable server, an invalid recipient - into a single boolean, so the
UI could only ever say "not configured / failed" regardless of which of those actually happened.
Fixed by giving `email_notifier.py`/`sms_notifier.py`/`telegram_notifier.py`/`slack_notifier.py`
each a `send_*_with_reason()` variant returning `(sent, reason)` with real, distinct reason codes
(`not_configured`, `no_recipient`, `auth_failed`, `unreachable`, `invalid_recipient`, `failed`,
`sent`) - never a guessed/fabricated one, only ever returned when the corresponding real
condition/exception occurred (e.g. `smtplib.SMTPAuthenticationError` → `auth_failed`,
`httpx.TransportError`/`ConnectionRefusedError` → `unreachable`). The original `send_email`/
`send_sms`/etc. functions are now thin wrappers over these, so every other caller (the dispatcher,
the alert/optimization evaluators) is completely unaffected - only `send_test_notification` was
changed to use the reason-returning variants. `NotificationSettingTestResult` gained `*_reason`
fields (email/secondary_email/sms/telegram/slack), and the Notification Settings page now shows a
distinct success/warning row per channel with the real reason spelled out, instead of one
collapsed sentence.

Live-verified against the real running API: `POST /notification-settings/test` now returns
`"email_reason": "not_configured"` (accurate for this environment) instead of a generic `false`.
To see a real `"sent"`/`"auth_failed"`/`"unreachable"` in this environment, set real
`SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM_ADDRESS` (or `TWILIO_ACCOUNT_SID`/
`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER`) in `.env` and restart the backend - the code path is
fully wired and tested; only real credentials are missing from this environment, not code.

## 9. Known Limitations (disclosed)

- **Node Failure/Container Failure require a kubeconfig mounted into the backend container** to
  activate against a real cluster in this `docker compose` topology - `docker-compose.yml` doesn't
  mount one by default (most environments running this platform have no cluster at all), so the
  feature is verified live via a temporary mount (§6.6) rather than the persistent dev stack. A
  deployment that *does* have a reachable cluster only needs to set
  `ALERT_KUBERNETES_MONITORING_ENABLED=true` and mount its kubeconfig.
- **Resource Optimization's alert can be pre-empted by auto-apply** being enabled (§6.3) - by
  design: an auto-applied recommendation means the system already self-corrected, so there is
  nothing pending for a human to act on. Disclosed rather than treated as a gap.
- **Storage and Disk are the same underlying signal** - this platform has no distinct
  filesystem/volume metric collector separate from `disk_usage_mb`. A genuinely independent
  Storage metric (e.g. a real volume/PVC usage source) would need new metric collection, not
  wiring - the same category of gap Phase 21 already disclosed for the platform's remaining
  unimplemented metrics.
- **Notification language is stored but not yet applied** - every notification template remains
  English-only; real per-language message templates would be a substantial follow-up, not a small
  extension.
- **API Latency/Error Rate/Node Failure/Container Failure have no per-cloud-account override** -
  disclosed in §4 as a deliberate scoping decision, not an oversight.
