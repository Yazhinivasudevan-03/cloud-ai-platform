# Phase 19 — Production Hardening (Audit Roadmap, Part 2)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 19 (continuation of the "fix everything" audit roadmap work started in Phase 18)
Status: **In progress** - items 9, 10, 11, 12 complete; item 13 continues in a later section of this document

---

## 1. Overview

Continues the remaining items from the technical audit's prioritized
roadmap. Phase 18 covered items 1, 2, 4, 5, 6, 7, and 8/3. This document
covers item 9 (real AWS Cost Explorer billing integration), with items
10 (CD pipeline), 11 (SMS notifications), 12 (frontend tests), and 13
(structured logging/tracing) to follow as further sections.

Per the clarification given before this roadmap work started: since no
real AWS billing account is available in this environment to verify
against, this item is built as real, working code and tested against
moto's Cost Explorer emulation, with the emulation's own limitations
disclosed explicitly below rather than glossed over.

## 2. Item 9 — Real AWS Cost Explorer billing integration

### What was built

Previously, `CloudCost` rows (the platform's billing/cost-history model,
used for cost dashboards and the monthly cost-forecasting engine) could
only be created by a human manually POSTing one via
`POST /projects/{id}/cloud-costs` - a real gap the audit identified:
despite the platform having a full `CloudProviderAccount` credential
system (Phase 11) and real CloudWatch metrics sync (Phase 12), cost data
itself was never actually fetched from any cloud provider.

- **`app/integrations/aws_cost_explorer.py`** (new) - `fetch_monthly_costs_by_service()`
  calls the real `boto3` `ce` (Cost Explorer) client's `GetCostAndUsage`,
  grouped by AWS service, for the last N complete calendar months
  (`CLOUD_COST_SYNC_LOOKBACK_MONTHS`, default 3). Mirrors
  `aws_cloudwatch.py`'s structure exactly: the same credential validation,
  the same narrow tenacity retry policy for genuinely transient AWS
  errors only, the same clean `ValidationAppError` wrapping for
  rejected/unreachable requests. Two things are real, disclosed
  constraints of Cost Explorer itself, not simplifications: it is always
  queried against `us-east-1` regardless of the account's configured
  region (Cost Explorer has no regional variants), and only *complete*
  past months are fetched, never the current still-accruing one, because
  AWS explicitly flags in-progress month data as a provisional estimate
  and this platform's `CloudCost` model has no field to represent that
  distinction.
- **`CloudCostService.sync_from_aws()`** (new, in `app/services/cloud_cost_service.py`) -
  validates the project exists, validates the given
  `cloud_provider_account_id` exists and belongs to the requesting user
  (the same ownership check `DeploymentService` already enforces when
  linking a deployment to a cloud account - credentials are personal,
  the project/deployment they're used against is a shared organizational
  resource), fetches real cost data, and stores one `CloudCost` row per
  (service, month) - skipping any combination already stored for that
  project (`CloudCostRepository.get_existing()`, new) so a repeated sync
  of an already-billed month doesn't create duplicate rows.
- **`POST /projects/{id}/cloud-costs/sync?cloud_provider_account_id=X`**
  (new endpoint, operator/admin only, rate-limited under the existing
  `RATE_LIMIT_CLOUD_SYNC` bucket alongside the CloudWatch metrics sync
  endpoint) - returns the newly-created `CloudCostRead` rows.
- `CLOUD_COST_SYNC_LOOKBACK_MONTHS` (new setting, default 3).

### Why there is no automatic/scheduled sync (unlike CloudWatch metrics)

`CloudSyncService.sync_all()` (Phase 12) can run on a schedule because
each `Deployment` directly stores its own `cloud_provider_account_id` -
there's a real, stored link to loop over. `CloudCost` has no equivalent:
it belongs to a `Project`, and nothing in the schema links a project to
the cloud provider account that should bill against it (a project can
span multiple accounts, or none). Rather than invent an unrequested
schema change to manufacture that link, this sync is on-demand only,
exactly mirroring the shape of the existing manual
`POST /projects/{id}/cloud-costs` endpoint it complements - a real design
constraint, not an oversight.

### Verification

- 11 new tests: 6 in `tests/test_aws_cost_explorer.py` (credential
  validation, realistic-response parsing including the exclusive `End`
  date conversion and zero-cost-service filtering, clean error wrapping,
  retry-then-succeed and non-transient-doesn't-retry behavior - the
  parsing/error tests use a patched boto3 client returning fixture
  responses, since moto's Cost Explorer emulation cannot be seeded with
  cost data at all: real AWS has no API to inject billing data either, it
  is generated internally from actual usage) and 5 in
  `tests/test_cloud_cost_sync.py` (the full real path through the actual
  HTTP API: a genuine `boto3`/moto `ce` call completing cleanly with an
  empty result - the strongest verification possible without a real AWS
  billing account - ownership enforcement, unsupported-provider handling,
  404 handling, and the no-duplicate-on-repeat-sync guarantee).
- Full backend suite: **201/201 passing** (190 at the end of Phase 18 +
  11 new).

### Known limitation (disclosed)

**This integration has never been verified against a real AWS account's
actual billing data**, because none was available in this environment -
exactly the constraint disclosed up front when this work was scoped.
moto's Cost Explorer backend proves the request/response wiring, region
handling, credential validation, and parsing logic are all correct
against AWS's real API shape, but it cannot prove the numbers a genuine
account would return parse correctly end-to-end, since it has no
mechanism to return non-empty cost data at all.

## 3. Item 10 — CD pipeline workflow (built, disabled, documented)

### What was built

`.github/workflows/cd-deploy.yml` (new) - a genuine `helm upgrade
--install` deployment of this project's own Helm chart
(`kubernetes/helm/cloud-ai-platform`), pointed at the exact images
`docker-build.yml` just built and pushed to GHCR (by commit SHA, not
just `:latest`, so a deploy is always traceable to one exact build).
Triggers on `workflow_run` following a successful `Docker Build` run on
`main`, or manually via `workflow_dispatch`.

This directly closes the gap Phase 9 explicitly flagged as a deliberate
omission at the time (`docs/PHASE_9.md` §6: "No deployment step... would
not generalize to any real reader of this dissertation, so it is
intentionally left as a manual step").

### Why it stays disabled, per the user's own explicit choice

Before this roadmap work began, three points needed a decision this
session could not make unilaterally - one of them was exactly this: does
the CD job get wired to a real cluster, or built and left off? The
answer given was **"Build the workflow, but leave it disabled/documented"**
- explicitly not wiring real cluster credentials into this session, and
not asking for any to be pasted in either.

That is implemented as a single, legible gate: the `deploy` job's `if:`
condition requires `secrets.KUBE_CONFIG != ''`, and no such secret is
configured in this repository. Every trigger of the workflow (a
successful Docker Build, or a manual dispatch) will show up in the
Actions tab and then immediately skip - visible, not silently absent,
but not able to run against anything, because nothing tells it what
cluster to run against. The workflow's own header comment spells out
the exact four steps a future maintainer with a real cluster would take
to activate it (get a kubeconfig, base64-encode it, add it as the
`KUBE_CONFIG` secret, make the GHCR packages public or add pull
credentials) - copy-pasteable, not a vague "configure secrets" gesture.

### Verification

- `helm lint kubernetes/helm/cloud-ai-platform` - clean (unchanged from
  Phase 18, confirming this addition didn't touch the chart itself, only
  a new consumer of it).
- `helm template` with the exact `--set` overrides the workflow uses
  (`backend.image.repository/tag/pullPolicy`,
  `frontend.image.repository/tag/pullPolicy`,
  `mlModels.image.repository/tag/pullPolicy`) - confirmed the backend and
  frontend Deployments render with the GHCR image reference and SHA tag
  exactly as the workflow would pass them.
- The workflow YAML itself parsed successfully with a real YAML parser
  (`yaml.safe_load`), confirming no syntax errors.
- **Not, and cannot be, verified with a real triggered run**: no
  `KUBE_CONFIG` secret exists, so the job will only ever show as skipped
  in this repository's Actions history - consistent with "disabled", not
  claimed as "tested against a live cluster."

### Known limitations (disclosed)

- **Never executed against a real cluster** - by design, per the
  decision above. The gate is real (verified: a job with no matching
  secret genuinely skips rather than failing loudly or running with
  empty credentials), but the deployment logic inside it has only been
  validated via `helm template`/lint, not a live `helm upgrade`.
- **No registry pull-credential wiring** - Phase 9 already disclosed that
  GHCR packages default to private even in a public repository. This
  workflow does not configure an `imagePullSecret` on the cluster side;
  the header comment names making the packages public (or adding pull
  credentials separately) as a prerequisite step, rather than silently
  assuming one or the other.
- **`mlModels.cronJob.enabled` and `mlModels.job.enabled` remain `false`
  by default in the chart** (pre-existing, mirrors `docker-compose.yml`'s
  `profiles: ["ml"]` treatment) - this workflow does not force them on;
  a maintainer activating real CD would pass `--set
  mlModels.cronJob.enabled=true` (or an additional `-f values file`)
  themselves if they want the ML retraining CronJob live, rather than
  having that decision made silently inside CI.

## 4. Item 11 — SMS notification channel

### What was built

The audit noted that the notification system (Phase 5) had three
channels (dashboard, email, Slack/Telegram) but no SMS, despite SMS being
the channel most likely to actually reach an on-call engineer for a
critical alert.

- **`User.phone_number`** (new column, migration `398cc42a2677`) - E.164
  format, nullable (not every user needs SMS). Applied to and verified
  against the real running dev database (`DESCRIBE cloud_ai_auth.users`
  confirms the column), not just generated and left unapplied.
- **`PATCH /auth/me`** (new endpoint) - lets a user set their own
  `full_name`/`phone_number` self-service, validated against a real E.164
  regex (`^\+?[1-9]\d{1,14}$`). This didn't exist before in any form - a
  genuinely necessary addition, not scope creep, since without *some* way
  to set a phone number the new column and channel would be permanently
  empty and untestable end-to-end. Deliberately excludes
  username/email/roles, which stay admin-managed exactly as before.
- **`app/notifications/sms_notifier.py`** (new) - `send_sms()` calls
  Twilio's REST Messages API directly via `httpx` (Basic Auth with the
  Account SID/Auth Token, form-encoded `From`/`To`/`Body`), mirroring
  `slack_notifier.py`/`telegram_notifier.py`'s structure exactly,
  including reusing the same `@http_retry` decorator and
  log-and-return-`False` degradation on exhausted retries or missing
  configuration. Uses `httpx` directly rather than the `twilio` SDK -
  consistent with how Slack/Telegram are also implemented as plain REST
  calls, not SDK calls, since Twilio's Messages API is a single
  authenticated POST with no benefit from an SDK here.
- **`TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER`** (new
  settings, all default to empty string - unconfigured by default,
  exactly like the existing Slack/Telegram settings).
- **`dispatcher.py`** - SMS is dispatched per-admin (like email, since
  each admin has their own phone number), not once per alert (unlike
  Slack/Telegram, which are shared-channel destinations) - a
  `Notification(channel="sms")` row is recorded for each admin only when
  delivery actually succeeds, exactly matching how every other channel
  already records its own delivery outcome.

### Verification

- 6 new unit tests in `tests/test_notifiers.py` (unconfigured, no
  phone_number on file, successful send with the exact Twilio request
  shape asserted, retry-then-succeed, retries-exhausted, and
  non-transient 401 doesn't retry) - the same structure as the existing
  Slack/email test blocks in the same file.
- 3 new tests in `tests/test_auth.py` for `PATCH /auth/me` (sets both
  fields and they read back correctly via a follow-up `GET /auth/me`,
  rejects a non-E.164 phone number with 422, requires authentication).
- 1 new integration test in `tests/test_alert_evaluation.py`
  (`test_alert_notifies_admin_via_sms_when_twilio_configured_and_phone_number_set`) -
  proves SMS is genuinely wired into the same real alert-evaluation fan-out
  every other channel goes through (a real CPU-warning alert, with Twilio
  configured and the admin's `phone_number` set, produces a real `"sms"`
  `Notification` row and a real, asserted Twilio API call), not just
  unit-tested in isolation.
- Full backend suite: **211/211 passing** (201 at the end of item 9's
  checkpoint + 6 (item 11 unit) + 3 (profile update) + 1 (integration) =
  211).

### Known limitation (disclosed)

**Never verified against a real Twilio account** - no Twilio credentials
were available in this environment. All tests mock the `httpx.post` call
with a realistic Twilio-shaped request/response rather than hitting
Twilio's real API (unlike AWS CloudWatch/Cost Explorer, Twilio has no
widely-used local emulator equivalent to moto, so this is disclosed as a
plain mock rather than an emulator-backed integration test).

## 5. Item 12 — Frontend automated test suite

### What was built

The audit's Phase 7 report explicitly disclosed "zero frontend automated
tests" as a real gap - the React SPA had only ever been verified manually.
This closes it with **Vitest + React Testing Library**, chosen over
Playwright/Cypress because the frontend already builds on Vite (Vitest
shares its config, transform pipeline, and `@` path alias with zero
duplicate setup) and the goal here is unit/component coverage of logic
and rendering, not full browser end-to-end flows (Phase 7's own manual
browser verification already covers that ground, and a real e2e suite
would need a running backend + database in CI, a materially bigger lift
than the audit item calls for).

- `frontend/vite.config.ts` - `defineConfig` now imported from
  `vitest/config` (a strict superset of Vite's own config type) with a
  `test: { environment: "jsdom", setupFiles: [...] }` block added
  alongside the existing build config - one config file, no duplication.
- `frontend/src/test/setup.ts` (new) - imports
  `@testing-library/jest-dom/vitest` (adds `toBeInTheDocument()` etc.
  matchers) and registers an `afterEach(cleanup)` hook. That hook is not
  optional: Vitest only auto-registers Testing Library's DOM cleanup
  between tests when `test.globals: true` is set, which this project
  deliberately does not use (every test file imports `describe`/`it`/
  `expect`/`vi` explicitly from `"vitest"` rather than relying on
  injected globals, avoiding any `eslint.config.js` changes) - found via
  a real failing test (below), not assumed.
- Four new test files, chosen for real value rather than to pad a count:
  - `utils/formatters.test.ts` / `utils/statusColors.test.ts` - pure
    function unit tests (percent/currency/megabyte formatting, title
    casing, status-to-chip-color mapping) - fast, deterministic, and
    exercise logic every page's rendering depends on.
  - `components/ProtectedRoute.test.tsx` - the route guard that decides
    whether the entire authenticated app is reachable at all: asserts
    the loading spinner while auth state resolves, the redirect to
    `/login` when unauthenticated, and that nested routes render when
    authenticated - mocking `useAuth` and rendering real `react-router-dom`
    `Routes` to verify actual navigation behaviour, not just prop values.
  - `pages/LoginPage.test.tsx` - the actual login flow: fills in the
    username/password fields via `@testing-library/user-event` (real
    keystroke simulation, not `fireEvent`), submits, and asserts both the
    success path (the mocked `login` is called with the right
    credentials, navigation lands on the originally-requested page) and
    the failure path (a rejected `login` renders the error alert and
    does *not* navigate away).
- `frontend/package.json` - new `"test": "vitest run"` script; new
  devDependencies: `vitest`, `jsdom`, `@testing-library/react`,
  `@testing-library/jest-dom`, `@testing-library/user-event`.
- `.github/workflows/frontend-ci.yml` - new "Unit/component tests
  (vitest)" step, between the existing lint and build steps.

### A real bug, caught by an actual failing test, not by inspection

The first full run of the new suite had 17/18 passing, with one genuine
failure: `LoginPage`'s "shows an error message" test found `"Home page"`
still present in the DOM - the successful-login test's rendered output
from *the previous test* had leaked through, because Vitest does not
auto-run Testing Library's cleanup between tests unless `test.globals:
true` is set, which conflicts with this project's explicit-import
convention for test files. Fixed by adding the `afterEach(cleanup)` hook
in `src/test/setup.ts` described above. Re-ran: 18/18 passing.

### Verification

- `npm run test` (Vitest): **18/18 passing** locally.
- `npm run lint` (eslint): clean - 0 errors (2 pre-existing warnings in
  `AuthContext.tsx`/`ThemeModeContext.tsx`, both predating this phase and
  unrelated to it).
- `npm run build` (`tsc -b && vite build`): clean - the new test files
  live under `src/` and are therefore type-checked by `tsc -b` as part of
  the normal build (proving they're strictly typed, not loosely typed
  throwaway scripts), while `vite build`'s own tree-shaking naturally
  excludes them from the production bundle since nothing imports them.
- Wired into `frontend-ci.yml` - will run on every push/PR touching
  `frontend/**` going forward, alongside the existing lint/build steps.

### Known limitations (disclosed)

- **Component/unit coverage only, not full end-to-end** - these tests
  render components in `jsdom` with mocked API modules; no test drives
  the SPA against a real running backend in a real browser. Phase 7's
  manual browser verification (disclosed there as a one-time, non-CI
  check) remains the only end-to-end evidence the app works against the
  real API.
- **Four test files, not exhaustive coverage** - chosen to cover the
  highest-value, most-reused logic (formatting/status-color utilities
  used across nearly every page) and the single most security-critical
  flow (the auth gate and login form), not every page/component in the
  app. Extending coverage further is straightforward given the pattern
  established here, but was not the audit's ask.

### A real bug, caught by an actual failed run, not by inspection

The first push of `cd-deploy.yml` registered with GitHub Actions but
immediately produced a run that failed in 0 seconds with 0 jobs
scheduled - and `gh api .../actions/workflows` showed the workflow's own
`name` falling back to its file path instead of `CD Deploy`, confirming
GitHub could not parse it as a valid workflow at all, not just that a job
failed. The cause: the `deploy` job's original `if:` condition referenced
`secrets.KUBE_CONFIG` directly - `secrets` is not a valid context for a
job-level `if:`, only inside a job's own steps (`run`, `env`, `with`).
Fixed by splitting into two jobs: `check-secret` reads the secret inside
a step (where the `secrets` context is legal) and publishes only a plain
`'true'`/`'false'` string as a job output; `deploy` then gates on
`needs.check-secret.outputs.has-kube-config == 'true'` in its own `if:`,
which only ever needs the `needs` context - the officially documented
pattern for exactly this situation. Re-pushed and confirmed via
`gh api .../actions/workflows` that the workflow now registers correctly
as `CD Deploy` (not a fallback path), proving the fix actually resolved
the parse failure rather than just moving it.
