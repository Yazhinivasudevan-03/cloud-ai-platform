# Phase 24 — Multi-Tenant SaaS Platform: Auth/Onboarding, Full Per-User Data Isolation, Real Multi-Cloud Sync, and a SaaS UI/UX Overhaul

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 24 (explicit request to convert the platform from a shared-organization internal tool into a
genuine multi-tenant SaaS product: proper signup/verification/login/reset flows, full per-user data
isolation across every domain object, real Azure/GCP cloud integrations alongside the existing AWS one,
and a matching SaaS-grade frontend)
Status: **Complete**

---

## 1. Overview

This was the largest phase of the project, requested and executed in three parts:

1. **Authentication & onboarding** — a real SaaS signup form (first/last name, email, mobile number,
   optional company, country, password/confirm), auto-generated usernames, email verification gating
   login, forgot/reset password, a "Remember Me" long-lived session, and an authenticated
   change-password endpoint.
2. **Full per-user data isolation** — the platform's entire core domain (Project → Microservice →
   Deployment → Pod → Metric/ResourceUsage → Predictions/AnomalyDetections/FailurePredictions →
   OptimizationRecommendations → CloudCost → Alerts) was previously a deliberately shared,
   single-organization model (documented in `project_router.py`'s own prior docstring: "any authorized
   staff can see all monitored infrastructure"). This phase converts it to genuine tenant isolation:
   a resource is visible only to its owning user, or a platform `is_superuser` — `admin` is now purely
   an app-management role *within* a tenant, not a cross-tenant data-access bypass.
3. **Real multi-cloud sync + a matching SaaS UI** — real Azure Monitor and Google Cloud Monitoring
   integrations alongside the existing AWS CloudWatch one (plus Azure Cost Management for billing), a
   multi-account filter on the dashboard, and a full frontend rebuild: public Landing Page, rebuilt
   Sign Up/Login, Email Verification/Forgot/Reset Password pages, a named-provider onboarding
   empty-state (AWS/Azure/Google Cloud/Oracle Cloud/IBM Cloud/DigitalOcean/Alibaba Cloud), an extended
   Profile page (personal + company details + security + connected accounts), and full sidebar
   navigation.

Every new integration follows this project's existing, established pattern (typed fetcher function,
credentials dict, `tenacity` retry on transient errors only, a `ValidationAppError` on real failures) —
nothing here is faked. Where a real limitation exists (GCP has no generalizable "give me my spend by
service" API the way AWS Cost Explorer/Azure Cost Management do — it requires the customer's own
BigQuery billing export), it is honestly reported as `COST_SYNC_PROVIDER_NOT_SUPPORTED`, matching this
project's consistent stance (SMTP/SMS reason-coding, deferred email delivery) of disclosing real gaps
rather than fabricating a fragile integration.

## 2. Database schema changes

All additive; no destructive migrations. Both new migrations back-fill existing rows with a
`server_default` where a `NOT NULL` column was added, so no existing user/account was ever locked out.

- **Migration `734043a1ade2`** — `cloud_ai_auth.users` gains:
  - `first_name`, `last_name`, `company_name`, `country` (all nullable `VARCHAR`)
  - `email_verified BOOLEAN NOT NULL DEFAULT 1` (server-default backfills all 53 pre-existing users
    as already-verified; new registrations default to `False` at the ORM level)
  - `email_verification_token_hash VARCHAR(64)`, `email_verification_expires_at DATETIME`
  - `password_reset_token_hash VARCHAR(64)`, `password_reset_expires_at DATETIME`
  - `phone_number`'s existing column is reused as the signup form's "Mobile Number" — not duplicated.
- **`is_superuser`** (pre-existing column) is repurposed as the actual platform-operator flag: distinct
  from the `admin` role, which is now tenant-scoped app management only.
- No schema change was needed for cloud-provider credentials (`CloudProviderAccount.credentials_encrypted`
  already stores an arbitrary encrypted key-value dict) or for cross-user isolation (every domain table
  already chains up to `Project.owner_id` via existing foreign keys) — isolation is enforced entirely in
  the application layer (see §4), not by new columns or constraints.

## 3. Auth flow

- **Sign Up** (`POST /auth/register`) — accepts the new field set; `username` is optional and
  auto-derived from the email's local part (collision-suffixed, e.g. `jdoe`, `jdoe2`) when omitted, so
  the new signup form never asks for one, while every pre-existing username-based caller (tests,
  scripts) keeps working unchanged. Issues a real single-use, SHA-256-hashed verification token
  (`app/utils/tokens.py`, mirrors password hashing); the raw token/link is returned in the response and
  logged (real SMTP delivery isn't wired up in this environment — the user's own explicit choice — so
  this is disclosed honestly, never faked as "email sent").
- **Email Verification** (`GET /auth/verify-email?token=`, `POST /auth/resend-verification`) — a fresh
  account cannot log in until verified (`403 EMAIL_NOT_VERIFIED`); resend is always a generic response
  regardless of whether the email exists or is already verified, to prevent account enumeration.
- **Login** (`POST /auth/login`) — now accepts either a username or an email as the identifier
  (`AuthService.authenticate()` tries `get_by_username()` then `get_by_email()`); gained an optional
  `remember_me` form field.
- **Remember Me** — `remember_me=true` issues a 30-day refresh token instead of the default 7-day one;
  the JWT's own `remember_me` claim carries the choice forward through `POST /auth/refresh`, so a
  remembered session keeps renewing at the long duration.
- **Forgot / Reset Password** (`POST /auth/forgot-password`, `POST /auth/reset-password`) — same
  hashed-single-use-token pattern as email verification, but a **much shorter** 1-hour expiry (a leaked
  reset link is more immediately dangerous than a leaked verification link) and the raw token is
  **never** returned over the API (only logged) — unlike registration, an anonymous caller here must
  never be able to tell whether an email exists from the response shape.
- **Change Password** (`POST /auth/change-password`, authenticated) — verifies the current password,
  then sets the new one; new for a logged-in user's own Profile/Security page (reset-password is
  token-based and only for a forgotten password).
- **Profile update** (`PATCH /auth/me`) — extended to also accept `first_name`/`last_name`/
  `company_name`/`country`.

## 4. Full per-user data isolation

- **`app/utils/ownership.py`** (new) — the one shared primitive: `raise_if_cannot_access_project(project,
  current_user)` raises `403 NOT_YOUR_PROJECT` unless `current_user.is_superuser` or
  `project.owner_id == current_user.id`. Every other resource in the chain resolves its own owning
  `Project` via a plain relationship walk (e.g. `deployment.microservice.project`,
  `pod.deployment.microservice.project`) and calls the same helper — no per-resource reimplementation.
- Applied to **every** read/write endpoint across Project, Microservice, Deployment, Pod, Metric,
  ResourceUsage, Prediction/AnomalyDetection/FailurePrediction, OptimizationRecommendation, and
  CloudCost. Global, parent-less listings (`GET /projects`, `GET /optimization-recommendations`,
  `GET /alerts`) gained a repository-level `owner_id` filter (`None` only for a superuser — every other
  caller is scoped to their own `current_user.id`).
- **Alert isolation** — `Alert` has three mutually-exclusive scopes (`deployment_id`, `project_id` for
  cost alerts, `user_id` for security alerts) plus a fourth: genuinely platform-wide, tenant-less alerts
  (API Latency/Error Rate/Node Failure/Container Failure — introduced in Phase 23). `AlertService`
  resolves the correct owner for whichever scope an alert actually has; the global `GET /alerts` listing
  uses a three-way `OR` across outer-joined Deployment→Microservice→Project and Project-direct paths,
  excluding platform-wide rows entirely for non-superusers.
- **Notification dispatcher fan-out** (`app/notifications/dispatcher.py`) — previously notified *every*
  admin-role user platform-wide for any alert (the old shared-org design). Now resolves the alert's real
  recipient(s): the deployment's project owner, the cost-alert project's owner, the security alert's own
  user, or — only for genuinely platform-wide alerts — every `is_superuser`. A superuser is **not**
  additionally paged for other tenants' scoped alerts (they can still see everything via the global
  listing endpoints, just aren't notified for it), mirroring how a real SaaS platform operator isn't
  paged per-customer.
- **Multi-account filtering** — `GET /microservices/{id}/deployments` gained an optional
  `cloud_provider_account_id` query filter (repository-level, additive), letting the dashboard narrow
  its view to one connected cloud account instead of always showing every one of the user's own
  deployments combined.

Every isolation change has an explicit cross-tenant test proving a second, non-owning user gets
`403 NOT_YOUR_PROJECT` (or `NOT_YOUR_ALERT`) on get/update/delete and is excluded from that resource's
list — not just that the owner's own access still works.

## 5. Real multi-cloud integrations

- **`app/integrations/azure_monitor.py`** (new) — real VM metrics via `azure-identity`
  (`ClientSecretCredential`) + `azure-monitor-query`'s `MetricsQueryClient` (Percentage CPU, Network
  In/Out Total). Memory/disk are reported as `0.0` with the limitation documented (require the Azure
  Monitor Agent, which this platform can't assume is installed) — the same honesty AWS's own
  `aws_cloudwatch.py` already established.
- **`app/integrations/azure_cost_management.py`** (new) — real monthly billing via
  `azure-mgmt-costmanagement`'s Query API, grouped by service, closed months only — Azure's direct
  equivalent of AWS Cost Explorer.
- **`app/integrations/gcp_monitoring.py`** (new) — real Compute Engine instance metrics via
  `google-auth` service-account credentials + `google-cloud-monitoring`'s `MetricServiceClient`
  (CPU utilization, network in/out). Same memory/disk-unavailable-without-agent honesty. GCP **cost**
  sync is deliberately not implemented (see `CloudCostService`'s own docstring) — unlike AWS/Azure, GCP
  has no generalizable spend-by-service API callable with just account credentials.
- `CloudSyncService._PROVIDER_FETCHERS` gained `"azure"`/`"gcp"` entries; `CloudCostService`'s
  (renamed) `_PROVIDER_COST_FETCHERS` gained `"azure"`. Both dicts were already written to be extended
  this way — no restructuring of either service was needed.
- 21 new unit tests (`test_azure_monitor.py`, `test_azure_cost_management.py`, `test_gcp_monitoring.py`)
  mocking each SDK client directly (no Azure/GCP emulator exists, unlike AWS's `moto`), covering
  success, incomplete credentials, a rejected API call, and transient-error retry behavior.

## 6. New/changed API surface

| Endpoint | Change |
|---|---|
| `POST /auth/register` | New signup field set; returns `verification_token`/`verification_link` |
| `GET /auth/verify-email` | New |
| `POST /auth/resend-verification` | New |
| `POST /auth/forgot-password` | New |
| `POST /auth/reset-password` | New |
| `POST /auth/change-password` | New |
| `POST /auth/login` | Accepts email or username; new `remember_me` field |
| `PATCH /auth/me` | New `first_name`/`last_name`/`company_name`/`country` fields |
| `GET /microservices/{id}/deployments` | New optional `cloud_provider_account_id` filter |
| Every Project/Microservice/Deployment/Pod/Metric/ResourceUsage/Prediction-family/Optimization/CloudCost/Alert endpoint | Now ownership-checked (403 `NOT_YOUR_PROJECT`/`NOT_YOUR_ALERT` for a non-owner) |

## 7. UI changes

- **Public** — new `LandingPage` + `PublicLayout` (top nav, Features/About/Contact, Login/Sign Up) at
  `/`; an already-authenticated visitor is redirected straight to `/dashboard`.
- **Sign Up** — rebuilt with the new field set (no username field); on success shows a "check your
  email" screen with the verification link surfaced directly (honest dev-environment disclosure, since
  real SMTP isn't wired up) instead of auto-logging in (a fresh account is unverified).
- **Login** — "Email" label (backend still accepts either), a "Remember me" checkbox, a "Forgot
  password?" link.
- **New pages** — `VerifyEmailPage`, `ForgotPasswordPage`, `ResetPasswordPage`.
- **Dashboard onboarding** — the existing empty-state now shows named connect buttons for all seven
  providers (AWS, Azure, Google Cloud, Oracle Cloud, IBM Cloud, DigitalOcean, Alibaba Cloud), each
  preselecting that provider in the existing `CloudAccountFormDialog`.
- **Profile** (`/profile`, extended `SettingsPage`) — editable first/last name, phone, company,
  country; a Security section (change password); a Connected Cloud Accounts summary; links out to
  Notification Settings for notification prefs/timezone.
- **Navigation** — sidebar expanded from just Dashboard(+Users) to Dashboard, Projects, Alerts,
  Optimization, Cloud Accounts, Notifications, Profile(+Users for admins).

## 8. Security improvements

- Genuine multi-tenant data isolation replaces the previous shared-organization model across the
  entire core domain — the single largest security change in this phase.
- Email verification gates login on a genuinely controlled address, closing the gap where any
  syntactically-valid email could self-register and immediately act.
- Password reset tokens are single-use, SHA-256-hashed at rest (never stored/logged in plaintext), and
  expire in 1 hour — deliberately shorter than the 24-hour email-verification token, since a leaked
  reset link is more immediately dangerous.
- Forgot-password and resend-verification are anti-enumeration by design: identical response regardless
  of whether the target email exists.
- Notification fan-out no longer leaks alert existence/content to every admin platform-wide — only the
  actual data owner (or, for genuinely tenant-less platform alerts, is_superuser) is notified.

## 9. Testing & verification

- **Backend**: 448/448 tests passing (up from a 412-test Phase 23 baseline), including ~60 new tests
  across auth (registration/verification/reset/remember-me/change-password), the three new cloud
  integrations, per-user isolation (one explicit cross-tenant-forbidden test per resource), and the
  rewritten alert-dispatcher/evaluation tests reflecting owner-based (not admin-based) notification.
- **Frontend**: 58/58 Vitest tests passing, `tsc -b` clean.
- **Live verification**: full containers rebuilt and brought up; the real register → verify-email →
  login (email + Remember Me) → profile-update → change-password → forgot-password round trip was
  exercised against the actual running backend through the frontend's nginx proxy (not mocked), with
  each step's real response inspected. Every new frontend route was confirmed to serve correctly via
  the SPA's `try_files` fallback. (No headless-browser tool was available in this environment to
  capture literal screenshots; verification was performed via direct HTTP/API round-trips against the
  live stack instead of a visual walkthrough.)

## 10. Follow-up hardening: monitoring pipeline isolation (post-launch)

A follow-up request asked for explicit confirmation that the monitoring/alert/AI pipeline is driven
exclusively by each user's own connected cloud accounts - no shared, platform-wide, demo, or
cross-tenant data. Investigation confirmed the following were **already true** from the work above and
needed no change:

- **Automatic collection**: `app/integrations/scheduler.py` already runs `CloudSyncService.sync_all()`
  on a fixed interval (`CLOUD_SYNC_INTERVAL_MINUTES`) against every cloud-linked deployment's real
  AWS/Azure/GCP account - not just on an operator's manual "sync now" request.
- **No demo/simulated data in the running app**: `ml-models/shared/synthetic_data.py` (a demo/training
  data generator) is only ever invoked via an explicit CLI subcommand
  (`run_pipeline.py generate-data`) that nothing in the container's default startup, the scheduled
  `ml-models-retrain` CronJob (`retrain-all` only), or `docker compose up` ever calls automatically.
  `database/schema/init.sql` seeds only roles/schema, never resource_usage/metrics/alerts.
- **Dashboards/alerts/notifications/AI reads**: already exclusively scoped to the current user via the
  Project→Microservice→Deployment ownership chain and the `owner_id`/`user_id` filters built earlier in
  this phase (§4) - confirmed via direct code audit of `CloudProviderAccountService` (self-service,
  `user_id`-scoped since Phase 11, no admin bypass at all) and `NotificationService` (always
  `user_id`-scoped).
- **Two clarifying decisions were confirmed directly with the user**: (1) keep per-user *isolation* as
  the only restriction - a deployment's alerts/predictions/optimization may still be driven by any
  legitimate resource_usage for that user's own deployment (real cloud sync **or** the existing manual
  ingestion API the test suite and ml-models pipeline both rely on), rather than rewriting the alert
  evaluator/optimization engine/test suite to require literal cloud-sync provenance; (2) the deliberate,
  disclosed exception remains unchanged - genuinely tenant-less platform alerts (API Latency/Error
  Rate/Node Failure/Container Failure, introduced in Phase 23) stay visible only to a platform
  `is_superuser`, since they describe the platform's own operational health, not any one tenant's cloud
  account.

What this pass actually **added** (additive, no rewrite):

- **`ResourceUsage.cloud_provider_account_id` / `ResourceUsage.owner_user_id`** and
  **`Alert.cloud_provider_account_id` / `Alert.owner_user_id`** - new computed model properties (backed
  by existing FK relationships, no migration) surfaced on `ResourceUsageRead`/`AlertRead` so every
  metric/alert response makes its owning cloud account and user explicit, rather than only enforced
  implicitly via the ownership chain. `cloud_provider_account_id` is `null` for a deployment with no
  linked cloud account (a real, honest null - not a fabricated value); `owner_user_id` is `null` only
  for a genuinely platform-wide alert.
- **`backend/tests/test_monitoring_pipeline_isolation.py`** (new, 2 tests) - a holistic, non-mocked
  proof of the entire pipeline for two independent tenants in one test: each connects a real AWS account
  (moto-emulated CloudWatch), links a deployment, syncs real metrics via the actual
  `POST /deployments/{id}/sync-cloud-metrics` path, triggers the real `AlertEvaluationService`, and
  confirms the real `dispatch()` notification fan-out - at every step, tenant A's data is fully absent
  from tenant B's reads and vice versa. A second test confirms a deployment with no connected cloud
  account still resolves a real, non-null owner while `cloud_provider_account_id` stays honestly null.

**Updated test count**: 455/455 backend tests passing (up from 448), 64/64 frontend tests passing.
