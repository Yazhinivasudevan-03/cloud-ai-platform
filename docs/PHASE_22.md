# Phase 22 — Multi-Timezone Support for Cloud Accounts

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 22 (explicit extend-only request: "add multi-timezone support... do not rewrite or replace the existing code")
Status: **Complete**

---

## 1. Overview

A real enterprise scenario the platform didn't handle: the *same* cloud
account often has resources spread across multiple regions - an AWS
account with an `eu-west-2` (London) deployment and an `ap-south-1`
(Mumbai) deployment at once, each needing its own correctly-DST-adjusted
local time, while everything already stored (and every existing API)
keeps working exactly as before.

This phase was explicitly scoped as **additive only**: no existing
table redesigned, no existing API changed shape, no existing feature
removed. Every new field is nullable and every new behaviour activates
only when a user opts a deployment into a configured timezone -
deployments that don't are byte-identical to pre-Phase-22 behaviour.

## 2. What Was Built

### Data model (additive only)

- **`CloudAccountTimezone`** (new table, migration `00d66ca4fca7`) - a
  one-to-many child of `CloudProviderAccount`: any number of
  `(region, availability_zone, label, timezone)` entries per account.
  `CloudProviderAccount.region` itself is untouched (stays a single
  string field) - this is the mechanism that makes "multiple deployment
  timezones per account" possible without redesigning the account table.
  `provider` is deliberately *not* duplicated onto this table - it's
  read via the relationship to `CloudProviderAccount.provider` at
  serialization time, so it can never drift out of sync.
  `timezone` is stored as a plain IANA identifier string (e.g.
  `"Europe/London"`) - never a raw UTC offset or fixed abbreviation,
  and the UTC offset itself is **never stored anywhere**, only ever
  computed fresh via `zoneinfo` at read time (see below), so it's
  always correct across Daylight Saving Time transitions.
- **`Deployment.cloud_account_timezone_id`** (new, nullable FK,
  `ondelete="SET NULL"`, migration `00d66ca4fca7`) - an *optional* link
  from the existing microservice-deployment concept to one entry in the
  new table. This deliberately disambiguates two different meanings of
  "deployment" that the request's language conflated: the platform's
  existing `Deployment` (a microservice instance) is not the same thing
  as a cloud account's regional/timezone presence: this FK is the bridge
  between them, not a rename or merge of either concept.

### Timezone conversion (stdlib only, zero new dependencies)

- **`app/utils/timezones.py`** (new) - `validate_iana_timezone`,
  `to_local`, `compute_utc_offset`, `format_local`, all built entirely
  on Python's stdlib `zoneinfo` module (its own bundled IANA tzdata).
  This is the only architecturally correct way to handle DST: the UTC
  offset for `"Europe/London"` depends on which specific instant you
  ask about (GMT in January, BST in July), not the zone name alone, so
  nothing in this module (or anything built on it) ever stores a
  static offset. Every timestamp elsewhere in this project is
  naive-UTC (no `tzinfo` attached, per the existing Phase 12/13
  convention) - these functions attach `timezone.utc` explicitly before
  converting, never assuming a caller already did.

### CloudAccountTimezone CRUD API (account-scoped, ownership-checked)

- **`GET/POST /cloud-provider-accounts/{id}/timezones`**,
  **`PUT/DELETE /cloud-provider-accounts/{id}/timezones/{timezone_id}`**
  (new) - mirrors the exact ownership-checked pattern
  `CloudAccountAlertThreshold` (Phase 20) already established: only the
  account's own owner may view/manage its timezone entries
  (`NOT_YOUR_CLOUD_ACCOUNT`, 403). Rejects invalid IANA identifiers
  (`INVALID_TIMEZONE`, 422) and duplicate `(region, timezone)` pairs on
  the same account (`CLOUD_ACCOUNT_TIMEZONE_EXISTS`, 409).
- **`GET /timezones`** / **`POST /timezones/validate`** (new,
  non-account-scoped) - the full IANA identifier list (via
  `zoneinfo.available_timezones()`) for the frontend's searchable
  dropdown, and a standalone validate-and-preview endpoint returning a
  clean structured `{valid, utc_offset, current_local_time, error}`
  result (HTTP 200 either way - an invalid zone is an expected,
  handled outcome, not a server error).

### Deployment linkage + validation

- **`DeploymentCreate`/`DeploymentUpdate`** extended with an optional
  `cloud_account_timezone_id` - the existing request/response shape is
  otherwise untouched.
- **`DeploymentService._check_timezone_belongs_to_account()`** (new) -
  mirrors the file's existing `_check_cloud_account_ownership` pattern:
  when a `cloud_account_timezone_id` is provided, it must belong to the
  *same* `cloud_provider_account_id` the deployment is itself linked to
  (`TIMEZONE_ACCOUNT_MISMATCH`, 422) - otherwise a deployment could
  display, say, a Mumbai local time while actually being linked to a
  different account's London-only credentials.

### Monitoring/alerts enrichment (additive fields only)

- **`ResourceUsage`** and **`Alert`** models gained computed `@property`
  accessors (`utc_timestamp`/`local_timestamp`/`deployment_timezone`/
  `region`/`provider` on `ResourceUsage`; `alert_time_utc`/
  `alert_time_local`/`deployment_timezone`/`region`/`provider` on
  `Alert`) that walk `deployment -> cloud_account_timezone` and
  `deployment -> cloud_provider_account` at serialization time and
  compute local time fresh via `format_local` - never a stored/cached
  value. `ResourceUsageRead`/`AlertRead` expose these as new, nullable
  response fields; every existing field (`recorded_at`, `triggered_at`,
  etc.) is completely unchanged. A deployment with no configured
  timezone gets `null` for all five - the exact same response shape as
  before Phase 22, just with five extra `null` keys.
- **`app/notifications/dispatcher.py`** - a new `_enrich_message()`
  helper appends Cloud Provider/Region/Deployment/Timezone/local+UTC
  alert time to the outgoing email/SMS/Telegram/Slack/Teams text, but
  only when the alert's deployment resolves a configured timezone;
  otherwise the text is byte-identical to before this phase. The
  dashboard `Notification.message` column is deliberately left as the
  plain `alert.message` in both cases - the richer context is
  available via the already-extended `AlertRead` API for anything
  reading alerts directly, not duplicated into the stored notification
  text.

### Frontend (additive components only)

- **`CloudAccountTimezonesCard.tsx`** (new) - a "Deployment time zones"
  section on the existing `CloudAccountDetailPage`, listing configured
  entries with Add/Edit/Delete, each showing its current UTC offset and
  local time (computed server-side, refreshed on every load).
- **`CloudAccountTimezoneFormDialog.tsx`** (new) - the Add/Edit form.
  The searchable IANA dropdown prefers the browser's own
  `Intl.supportedValuesOf('timeZone')` (zero network round-trip) and
  falls back to the backend's `GET /timezones` only if the browser API
  is unavailable; selecting a zone previews its live UTC offset/local
  time via `POST /timezones/validate`.
- **`TimeModeToggle.tsx`** / **`AlertTimeCell.tsx`** (new, shared) - a
  UTC/"Deployment local" toggle and the cell renderer that uses it,
  wired into the alert tables on `AlertsPage.tsx`,
  `CloudAccountDetailPage.tsx`, and `DeploymentDetailPage.tsx`
  (Alerts tab), plus the resource-usage chart's x-axis labels on
  `DeploymentDetailPage.tsx` (Overview tab). An alert/metric with no
  configured timezone renders identically regardless of which toggle
  position is selected.
- `types/index.ts` / `cloudProviderAccountsApi.ts` extended additively
  (new interfaces, new API methods) - no existing interface field or
  method signature changed.

## 3. A Test-File Ordering Bug Found (and fixed) During This Phase

While appending new tests to the end of `test_alert_evaluation.py`, an
`Edit` replacement was anchored on a code fragment that (unnoticed at
the time) already had its closing `if/else` assertions living
immediately after it in the file. The replacement inserted a *second*
copy of that `if/else` after the newly-added test functions instead of
before them, leaving a stray, undefined-variable fragment
(`expected_alert_type`) dangling inside the second new test. Caught
immediately by the full suite run (`NameError`, not a silent pass) and
fixed by deleting the misplaced duplicate block - the original,
correctly-placed `if/else` for `test_network_threshold_tiers` was
untouched. Lesson: when appending near the end of a file, read far
enough past the anchor point to see what already follows it, not just
up to where the anchor text ends.

## 4. Live Verification (not just unit tests)

Rebuilt and recreated the real `cloud-ai-backend`/`cloud-ai-frontend`
containers (confirmed `alembic current` = `00d66ca4fca7 (head)`, already
applied). Via the real HTTP API against the live dev database:

1. Created an AWS account with two timezone entries (`eu-west-2` /
   `Europe/London`, `ap-south-1` / `Asia/Kolkata`), an Azure account
   with `uksouth` / `Europe/London`, and a GCP account with
   `asia-south1` / `Asia/Kolkata` - the exact four scenarios named in
   the request (AWS London, AWS Mumbai, Azure UK South, GCP Mumbai).
2. Linked deployments to each entry, then posted real `resource_usage`
   rows:

   | Scenario | UTC posted | Local returned |
   |---|---|---|
   | AWS London (`Europe/London`) | `2026-08-15T17:35:00` | `2026-08-15 18:35 BST` |
   | AWS Mumbai (`Asia/Kolkata`) | `2026-08-15T17:35:00` | `2026-08-15 23:05 IST` |
   | Azure UK South (`Europe/London`, January) | `2026-01-15T14:20:00` | `2026-01-15 14:20 GMT` (no DST) |
   | GCP Mumbai (`Asia/Kolkata`) | `2026-01-15T14:20:00` | `2026-01-15 19:50 IST` (India never observes DST) |

   The London/Mumbai August result reproduces the request's own worked
   example exactly (18:35 BST / 23:05 IST from the same 17:35 UTC
   instant); the January result confirms the London entry correctly
   flips to GMT outside BST rather than a stale cached offset.
3. Ran `POST /alerts/evaluate` for real against the London (65% CPU)
   and Mumbai (90% CPU) deployments - both alerts fired
   (`cpu_elevated`/warning, `cpu_high`/critical) with
   `alert_time_local`/`deployment_timezone`/`region`/`provider`
   correctly resolved and `notifications_sent` confirming dispatch.
4. Confirmed `GET /timezones` includes `Europe/London`/`Asia/Kolkata`
   and `POST /timezones/validate` correctly accepts a real zone
   (returning a live UTC offset/local time) and rejects a garbage
   string with a clean `{valid: false, error: "..."}` (HTTP 200, not a
   thrown error).
5. **Regression check**: created a plain deployment with no
   `cloud_account_timezone_id` and posted resource usage to it -
   `utc_timestamp` was populated (mirrors `recorded_at`, unchanged
   behaviour) while `local_timestamp`/`deployment_timezone`/`region`/
   `provider` were all `null`, confirming existing/unconfigured
   deployments are completely unaffected.

## 5. Verification Summary

- Backend: **310/310 passing** (279 at the end of Phase 21 + 31 new: 8
  in `test_timezones.py`, 9 in `test_cloud_account_timezones_api.py`, 4
  in `test_timezone_router.py`, 4 in `test_deployments.py`
  (timezone-linkage ownership validation), 2 in `test_metrics.py`
  (resource-usage enrichment, incl. a regression test for the
  no-timezone case), 2 in `test_alert_evaluation.py` (alert
  enrichment, incl. a regression test), 2 in
  `test_notification_dispatcher.py` (notification-text enrichment,
  incl. a byte-identical-when-unconfigured regression test).
- Frontend: 20/20 Vitest passing (unchanged count - this phase's
  frontend work was new cards/dialogs/shared components verified via
  `tsc -b` type-checking and the live-verification pass above, not new
  component-level test files), `tsc -b` clean, Vitest clean.
- Live-verified against the real running stack and real dev database,
  as detailed in section 4 - not simulated.

## 6. Known Limitations (disclosed)

- **The new frontend components (`CloudAccountTimezonesCard`,
  `CloudAccountTimezoneFormDialog`, `TimeModeToggle`, `AlertTimeCell`)
  were verified via `tsc -b` type-checking, the existing Vitest suite,
  and the live backend API contract they consume (section 4) - not a
  real browser click-through, consistent with Phase 7's disclosed
  limitation on visual browser verification in this environment.
- **The searchable IANA dropdown's live preview depends on the
  browser's own `Intl.supportedValuesOf('timeZone')`** - supported by
  every current evergreen browser, with the backend's `GET /timezones`
  as a fallback only for browsers that lack it (very old browsers). Not
  a gap in this platform, just worth naming since it's a browser
  capability dependency rather than something entirely under this
  codebase's control.
- **The resource-usage chart's x-axis local-time labels use the
  backend's pre-formatted `local_timestamp` string directly** (e.g.
  `"2026-08-15 23:05 IST"`) rather than a shorter chart-optimized
  format - acceptable for the toggle's purpose but slightly longer than
  the existing UTC-mode tick labels.
- **Cost alerts (Phase 21, project-scoped) never resolve a timezone** -
  they have no `deployment_id`, so `deployment_timezone`/`region`/
  `provider`/`alert_time_local` are always `null` for them, which is
  correct (a cost alert has no single deployment to derive a timezone
  from) but worth naming explicitly since it's the one alert type this
  phase's enrichment structurally cannot reach.
