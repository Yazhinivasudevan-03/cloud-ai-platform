# Phase 20 — Notification Settings + Per-Account Alert Thresholds

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 20 (follow-up to a 13-task "make this production-ready" mega-request)
Status: **Complete**

---

## 1. Overview

After Phase 19 shipped, a large 13-task request arrived asking for a full
alerting/monitoring rebuild, framed around a claim that alerts were being
generated from "dummy values, random numbers, mock APIs... simulated
monitoring." Rather than executing that blind, a fork audit was run first
against the actual codebase (not memory of what was true when it was
built). The audit's finding: **the premise was false** - no fake-data path
exists anywhere in the real alert/metrics pipeline; the only synthetic
data in the repo is isolated load-test/pytest fixtures, both posting
through the real API, never a shortcut into it. What the 13 tasks
actually described was a real, substantial *feature expansion* on top of
an already-real foundation - more metric types, per-account thresholds, a
real settings page, a richer notification model, real-time push - not a
rebuild of something broken.

Given the scope, the user picked one concrete slice to build first:
**Notification Settings page + per-cloud-account alert thresholds**. This
document covers that slice.

## 2. What Was Built

### Per-user Notification Settings

- **`NotificationSetting` model** (new, migration `04ec0076aed1`) - one
  row per user: channel enable flags (email/SMS/Telegram/Slack/Teams),
  instant-alerts/daily-summary/alert-sound toggles, a do-not-disturb
  window (`dnd_start_time`/`dnd_end_time`/`timezone`), and a single
  encrypted JSON blob (`credentials_encrypted`) holding any per-user
  Telegram bot token/chat ID or Slack/Teams webhook override - reusing
  `app/utils/crypto.py`'s existing Fernet-based
  `encrypt_credentials`/`decrypt_credentials` (the same mechanism
  `CloudProviderAccount` already uses) rather than inventing a second
  encryption scheme. Lazily created on first access (get, save, or the
  first alert dispatched to that user - whichever comes first), not at
  registration - most users never touch it, and its absence is a
  well-defined "all defaults" state.
- **`GET/PUT /notification-settings`, `POST /notification-settings/test`**
  (new) - self-service, rate-limited (`RATE_LIMIT_NOTIFICATION_TEST`,
  5/hour - it sends real messages through paid/rate-limited third-party
  APIs). Credentials are write-only, mirroring
  `CloudProviderAccountRead`'s existing convention: a client can set or
  overwrite a Telegram token/Slack webhook but can never read a
  previously stored secret back out - only a `*_configured` boolean per
  credential.
- **`app/notifications/teams_notifier.py`** (new) - Microsoft Teams via
  an Incoming Webhook, structurally identical to `slack_notifier.py`.
  Built because leaving a `teams_webhook_url` field in the credentials
  blob with nothing that ever sent through it would have been exactly
  the kind of dead configuration surface this phase's own audit flagged
  elsewhere (the pre-existing, unused `Setting` model).
- **`app/notifications/dispatcher.py` rewritten** to read each admin's
  `NotificationSetting` instead of notifying every admin across every
  channel unconditionally: a channel the admin hasn't enabled is never
  attempted; a do-not-disturb window (with correct midnight-wrap
  handling) suppresses email/SMS/Telegram/Slack/Teams but **never** the
  in-app dashboard notification - a user's own inbox should never
  silently lose an alert because of a preference toggle, only the
  out-of-band pings are suppressed. When multiple admins resolve to the
  *same* Telegram/Slack/Teams destination (the default, before anyone
  configures a personal override), that destination is posted to once
  per alert, not once per admin - a shared channel doesn't get spammed
  with duplicate copies just because per-user preferences now exist.
- **`PATCH /auth/me` wired into the frontend for the first time** - this
  endpoint existed since Phase 19 but had no UI consumer; the phone
  number field it exposes is now genuinely settable from the
  Notification Settings page (self-service, required for the SMS
  channel to have anywhere to send to).
- **`frontend/src/pages/NotificationSettingsPage.tsx`** (new), reached via
  a new "Notification Settings" item in the account menu (`UserMenu.tsx`)
  - matching this app's existing convention that personal/account-level
  pages (like "Settings") live in the user menu, not the primary sidebar.
  Covers every field from the request: contact info, per-channel
  enable/credential fields with "already configured" chips, delivery
  preferences, do-not-disturb window + timezone, save, test notification
  (with a live per-channel result), and a link out to the existing
  Notification history page rather than duplicating it.

### Per-cloud-account CPU/memory alert thresholds

- **A real gap closed first**: the audit found `AlertEvaluationService`
  only ever alerted on CPU - `memory_usage_mb` was read by
  `OptimizationService`'s recommendations but never turned into a real
  `Alert`. Building per-account *memory* threshold overrides with no real
  memory-alerting behavior behind them would have been exactly the same
  dead-configuration problem as the Teams webhook above, so real 3-tier
  memory alerting was added first: `ALERT_MEMORY_WARNING_THRESHOLD`/
  `_CRITICAL_/_SATURATED_THRESHOLD` (60/80/90 - the tiers actually
  requested; CPU's own historical 60/80/100 is left unchanged so as not
  to alter already-tested behavior for a metric that already worked),
  new `memory_elevated`/`memory_high`/`memory_saturated` alert types,
  skipped entirely (like the optimization engine already does) when a
  deployment has no configured `memory_limit_mb`.
- **`CloudAccountAlertThreshold` model** (new, migration `99e3ad159808`)
  - one row per `CloudProviderAccount`, six nullable override fields (CPU
  and memory, warning/critical/saturated). Any field left null falls
  back to the platform-wide `Settings` default for that exact tier, so an
  account only needs to override what it actually wants changed.
  Deliberately scoped to CPU and memory only, not the ~10 other metrics
  the original request listed (disk, network, cost, API latency, pod/node
  health, etc.) - those have no real evaluator turning them into an Alert
  yet (confirmed by the audit), and a threshold field with nothing real
  to apply against is precisely the anti-pattern this whole phase set out
  to avoid.
- **`GET/PUT /cloud-provider-accounts/{id}/alert-thresholds`** (new,
  ownership-checked like every other self-service cloud-account
  endpoint) - `PUT` validates that the *effective* (override-or-default)
  tiers are strictly ascending per metric group, so a custom
  `cpu_warning_threshold` can never be set above the (possibly default)
  `cpu_critical_threshold`, which would make the warning tier
  unreachable.
- **`AlertEvaluationService` resolves the deployment's linked account's
  override**, field by field, before evaluating CPU/memory conditions -
  a deployment with no linked account (or an account with no override
  row) behaves exactly as before.
- **`frontend/src/components/CloudAccountAlertThresholdsCard.tsx`** (new)
  - a card on the Cloud Account detail page showing all six tiers, with
  the platform default shown as each blank field's placeholder.

## 3. A Real Test-Isolation Bug Found and Fixed

While running the full suite after this batch, `test_auto_apply_disabled_by_default_leaves_recommendation_pending`
(Phase 19) failed - not because of anything in this phase's own code, but
because `OPTIMIZATION_AUTO_APPLY_ENABLED=true` had been set in the
project's root `.env` (to demo that feature live against the real dev
stack) and `docker compose run`'s test container inherits the same
service `environment:` block as the real `backend` service, silently
leaking that host-local setting into the test run and making a
default-off assertion fail non-deterministically depending on developer
machine state. Fixed the same way the suite already handles
`MYSQL_DATABASE`/`OTEL_ENABLED`: `tests/conftest.py` now forces
`OPTIMIZATION_AUTO_APPLY_ENABLED=false` before the app is ever imported,
regardless of the environment it's run in.

## 4. Live Verification (not just unit tests)

Rebuilt and restarted the real `cloud-ai-backend`/`cloud-ai-frontend`
containers and ran a real end-to-end chain against the live dev database
via the actual HTTP API (not the test suite):

1. `PUT /notification-settings` with a Slack webhook + DND window +
   timezone - confirmed via `SELECT ... FROM notification_settings` that
   `credentials_encrypted` contains a genuine Fernet token, not the
   plaintext webhook URL anywhere in the column.
2. `POST /notification-settings/test` - `email_sent: false` (SMTP
   correctly unconfigured), `slack_sent: false` (a real HTTP POST to a
   fake webhook URL was genuinely attempted and failed after retries,
   not skipped), `sms_sent`/`telegram_sent: null` (disabled channels
   correctly never attempted).
3. `PUT /cloud-provider-accounts/{id}/alert-thresholds` with a custom
   `cpu_warning_threshold: 45.0`, then linked a real deployment to that
   account, posted a real `resource_usage` row (`cpu_usage_percent: 50.0,
   memory_usage_mb: 950.0` against a `memory_limit_mb: 1000`), and ran
   `POST /alerts/evaluate`. Result, read directly from the `alerts`
   table:

   | alert_type | severity | threshold_percent | message |
   |---|---|---|---|
   | `cpu_elevated` | warning | **45** | "CPU usage at 50.0% - above warning threshold" |
   | `memory_saturated` | critical | 90 | "Memory usage at 95.0% of the configured limit - at capacity" |

   50% CPU would **not** have alerted under the platform-wide default
   (60%) - it only fired because the custom per-account override (45%)
   was genuinely read and applied. `memory_saturated` is a real alert
   type that did not exist before this phase, firing correctly off real
   data.

## 5. Verification Summary

- Backend: **255/255 passing** (227 at the end of Phase 19 + 28 new: 5
  in `test_notification_dispatcher.py`, 6 in
  `test_notification_settings_api.py`, 5 in `test_notifiers.py`
  (Slack/Telegram per-user override + Teams), 7 in
  `test_alert_evaluation.py` (memory tiers + per-account CPU override),
  5 in `test_cloud_account_alert_thresholds_api.py`).
- Frontend: 20 Vitest tests passing (18 at the end of Phase 19 + 2 new
  for `NotificationSettingsPage`), `npm run lint` clean, `npm run build`
  clean.
- Live-verified against the real running stack and real dev database, as
  detailed in section 4 - not simulated.

## 6. Known Limitations (disclosed)

- **Daily summary is a stored preference with no scheduled job behind it
  yet** - `daily_summary_enabled` is saved and returned correctly, but no
  scheduler currently reads it and sends an actual daily digest. Building
  that digest job was out of scope for this slice.
- **Per-account thresholds cover CPU and memory only** - by design, per
  section 2 above, since no other metric has a real alert evaluator yet.
  Extending the alert engine to disk/network/cost/latency/etc. (part of
  the original 13-task list, not chosen for this slice) would be a
  natural, and now structurally straightforward, follow-up: each new
  metric would need its own `_<metric>_condition()` in
  `AlertEvaluationService` plus matching override columns on
  `CloudAccountAlertThreshold`.
- **No WebSocket/SSE** - the dashboard and alert views still poll via
  React Query, unchanged in this phase; genuine real-time push was a
  separate item in the original request, not part of this slice.
- **Alert sound is a stored per-user preference with no frontend audio
  playback wired to it yet** - saved and returned correctly, but nothing
  in the browser currently plays a sound when a new alert arrives.
