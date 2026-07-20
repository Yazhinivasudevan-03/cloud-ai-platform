# Phase 14 — Consolidated Cloud Account Usage View

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 14 (post-completion feature addition, beyond the original 10-phase plan)
Status: **Complete and verified**

---

## 1. Overview

Requested directly as "make the platform to letting users to connect
their cloud accounts so shows the notifications and cpu memory usages
and all." Investigation first, before writing any code: connecting cloud
accounts (Phase 11), syncing real CPU/network metrics from them
(Phase 12), and alerting/notifications (Phase 5) all already existed -
but there was a genuine gap. A user could link a deployment to a cloud
account and sync its metrics, but the only place to actually *see* that
usage was the one deployment's own detail page - there was no consolidated
view showing, for a given cloud account, every deployment linked to it
and its live usage at a glance. This phase closes exactly that gap.

## 2. What Was Already Working (verified, not rebuilt)

- **Notifications already fire from real cloud-synced data with zero extra
  wiring.** The alert evaluation job (`alert_evaluation_service.py`) reads
  the most recent `resource_usage` row per deployment regardless of
  whether it was manually posted or written by Phase 12's CloudWatch
  sync - same table, same query. A CPU threshold breach on real,
  cloud-synced data already triggers an alert and a notification exactly
  as it would for manually-ingested data.
- **Cloud account connection itself** (any provider, unlimited count,
  per-account region) was already fully self-service since Phase 11.

## 3. What Was Missing (the actual gap, closed by this phase)

- No page showed, for one cloud account, the set of deployments linked to
  it and their latest CPU/memory/network in one place - a user had to
  know which deployments were linked and open each one's "Cloud Sync" tab
  individually to see anything.
- The Dashboard has no resource-usage charts at all (by design - it's a
  cross-cutting summary of alerts/recommendations, not a metrics view);
  a consolidated per-account view was the more targeted fix and was
  chosen deliberately over adding unrelated charts to the Dashboard.

## 4. What Was Built

- **`GET /api/v1/cloud-provider-accounts/{account_id}/deployments`** - new
  endpoint (self-service, ownership-checked exactly like every other
  CloudProviderAccount endpoint) returning every deployment linked to
  that account, each paired with its most recent `resource_usage` row (or
  `null` if never synced/recorded yet) - `CloudAccountDeploymentSummary`.
- **`DeploymentRepository.list_by_cloud_account`** and
  **`ResourceUsageRepository.get_latest_for_deployment`** - two small,
  focused repository methods; the service composes them rather than
  writing a new bespoke query.
- **Frontend: a "View usage" action on the Cloud Accounts page.** Clicking
  it opens a dialog listing every linked deployment as a card - name
  (linking straight to that deployment's own detail page), namespace,
  resource identifier, and either CPU/Memory/Network chips (if synced) or
  a plain "Never synced yet" chip (if not) - reusing the exact
  `ResourceUsage` shape and formatters already used elsewhere in the app,
  not a new data model.

## 5. Architecture Decisions

### A read-only summary endpoint, not a new domain concept
`CloudAccountDeploymentSummary` is not stored anywhere - it's assembled
on request from two existing tables (`deployments`, `resource_usage`).
There was no reason to introduce a new persisted "usage summary" entity
just to answer "what's linked to this account and what's its latest
reading" - that's exactly what a read endpoint composing two existing
repositories is for.

### Reused `ResourceUsageRead` directly rather than a parallel schema
The summary's `latest_usage` field is the exact same `ResourceUsageRead`
schema the per-deployment resource-usage endpoints already return, so the
frontend's existing formatters (`formatPercent`, `formatMegabytes`,
`formatDateTime`) work unmodified - no new type needed on either side
beyond the thin wrapper describing which deployment a reading belongs to.

### A dialog on the existing Cloud Accounts page, not a new route
The "at a glance" requirement is naturally scoped *per account* - a user
wants to see "what's linked to my AWS account," not a global cross-account
firehose. Surfacing it as an action on the existing per-row account table
(rather than a new top-level page or a Dashboard widget) keeps the
information exactly where a user would look for it, without adding new
navigation.

## 6. Verification Results

- Backend test suite: **155/155 passing** (149 existing + 6 new): empty
  list when nothing is linked, a linked deployment with no usage yet
  shows `latest_usage: null`, a linked deployment with a recorded reading
  shows the correct values, an account only shows its own linked
  deployments (not another account's), 403 for another user's account,
  404 for a nonexistent account.
- Live API verification through the running Docker Compose stack:
  registered a fresh user, granted `operator` via direct MySQL grant
  (registration always defaults to `viewer`), created a cloud account,
  linked a deployment, confirmed the endpoint returns `latest_usage: null`
  before any usage exists, posted a resource-usage snapshot, confirmed
  the endpoint immediately reflects the real recorded values.
- `tsc --noEmit` and `eslint` both clean on every modified frontend file.
- Live browser verification of the "View usage" dialog: correct MUI
  styling, deployment card showing the real synced CPU/memory/network
  values, a working link through to the deployment's own detail page, and
  a correct empty-state message for an account with nothing linked yet.

## 7. Known Limitations (disclosed, not hidden)

- **Memory usage in the chip is only ever genuinely non-zero for
  providers/instances that actually report it.** As documented in
  Phase 12, AWS EC2's basic monitoring never exposes memory without the
  CloudWatch Agent - this view faithfully displays whatever the sync
  wrote (including a real `0.0`), it does not fabricate or estimate a
  different number.
- **No auto-refresh while the dialog is open.** Usage is fetched once
  when the dialog opens; re-opening it (or a page refresh) picks up
  anything synced since, consistent with how the rest of the app's
  React Query-backed views behave (no page currently polls live).
