# Phase 16 — Per-Account Monitoring as the Platform's Primary View

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 16 (post-completion feature addition, beyond the original 10-phase plan)
Status: **Complete and verified**

---

## 1. Overview

Requested directly, reacting to how the app had grown across Phases
11-15: "remove the buttons from ... the left side panel or the front
page ... make the critical recommendations and recent alerts everything
show after connect the users cloud account ... the main purpose of the
project is to show the monitoring of cloud usage, cpu usage, memory
usage of the respected each users cloud accounts ... show the alerts for
each accounts separately ... make sure users can add unlimited accounts
without lagging."

This is a restructuring, not a new capability: it re-centers the
platform's navigation and Dashboard around **per-cloud-account
monitoring** - the stated core purpose - rather than a flat set of
sidebar links to generic, platform-wide lists.

Before making any change, four genuinely ambiguous/conflicting
sub-requests were clarified directly with the user rather than guessed
at (see the four `AskUserQuestion` decisions this phase implements):
remove the *sidebar* duplicates (keep the Dashboard as the single entry
point); *hide* the Recent alerts/recommendations panels entirely until a
cloud account exists (not just re-scope their content); build alerts
"per account" as a full *dedicated page*, not an addition to the
existing quick-look dialog; and treat "unlimited accounts without
lagging" as something to *verify*, fixing only if a real problem turned
up.

## 2. What Was Built

- **Sidebar trimmed to just "Dashboard"** (+ "Users" for admins).
  Projects/Alerts/Optimization/Notifications/Cloud Accounts were removed
  as direct nav links - all of them are still real pages, still reachable
  (from the Dashboard's stat cards, the Cloud Accounts panel, and the new
  detail page), just no longer duplicated as standing sidebar buttons.
- **Dashboard's "Recent alerts"/"Recent optimization recommendations"
  panels now hidden entirely** until the user has connected at least one
  cloud provider account. Once they have ≥1, both panels appear exactly
  as before (unchanged content - this phase only changes *whether* they
  show, not *what* they show).
- **A new dedicated page per cloud account**, `/cloud-accounts/:accountId`
  (`CloudAccountDetailPage.tsx`): the account's header (name, provider,
  region, identifier), its linked deployments with live CPU/memory/
  network (reusing the Phase 14 data), and a new **"Active alerts for
  this account"** section - genuinely scoped to only that account's own
  linked deployments, not the platform-wide alert feed. The "Monitor"
  buttons on the Dashboard's Cloud Accounts panel and the Cloud Accounts
  page's table now navigate here; the old quick-look popup
  (`AccountUsageDialog`) was deleted as dead code once nothing referenced
  it anymore.
- **New backend endpoint**: `GET /cloud-provider-accounts/{id}/alerts` -
  every active alert for deployments linked to that specific account,
  ownership-checked exactly like every other CloudProviderAccount
  endpoint. Backed by a new `AlertRepository.list_active_for_deployments`
  (one query across a set of deployment IDs, not N+1 queries) and
  `CloudProviderAccountService.list_active_alerts`.
- **Scale verified, not just assumed**: created 60 real cloud accounts
  via the actual API for a test user and confirmed live, in a real
  browser, that the Dashboard and the (paginated) Cloud Accounts page
  both load quickly and handle pagination smoothly with no lag, freeze,
  or crash.

## 3. Architecture Decisions

### Hide, don't re-scope
The alternative considered for the Dashboard's alert/recommendation
panels was keeping them always visible but filtered to only cloud-linked
deployments. The user explicitly chose full visibility-gating instead:
nothing shows until a cloud account exists, then everything shows exactly
as before. This is a simpler rule with one condition, not a permanent
filter that would need to stay in sync with "which deployments count as
cloud-linked" as that set changes.

### A full page, not an extension of the existing dialog
The Phase 14 `AccountUsageDialog` already showed an account's linked
deployments' usage; the natural incremental move would have been adding
an alerts list inside that same dialog. The user chose a dedicated page
instead - more room for a genuine alerts table (sortable columns, room to
grow) than a popup allows, and it gives every cloud account a real,
linkable URL (`/cloud-accounts/:id`) rather than state that only exists
while a dialog happens to be open. The dialog itself was deleted rather
than kept as an unused alternative path once both call sites (Dashboard,
Cloud Accounts page) switched to navigation.

### One query across all linked deployments, not one alert query per deployment
`AlertRepository.list_active_for_deployments` takes a list of deployment
IDs and issues a single `WHERE deployment_id IN (...)` query, rather than
looping and calling the existing single-deployment method once per
linked deployment. With the "unlimited accounts, unlimited deployments"
requirement already established (Phase 11), an account with many linked
deployments must not turn "show me this account's alerts" into an
N-query operation.

### Verify first, change code only if broken
Given the explicit choice to verify rather than pre-emptively add new
pagination/limits, the existing controls already in place (20/page on
the full Cloud Accounts table, a 10-account cap on the Dashboard's
summary panel) were tested directly with 60 real accounts rather than
assumed sufficient or rebuilt from scratch. They held up with no changes
needed.

## 4. Verification Results

- Backend test suite: **169/169 passing** (164 existing + 5 new for the
  `/alerts` endpoint: empty when none, shows an active alert for a linked
  deployment, isolates alerts correctly between two different accounts,
  403 for another user's account, 404 for a nonexistent account).
- `tsc --noEmit` and `eslint .` both clean across the frontend - zero
  errors, zero new warnings.
- **A real deployment mistake was caught and fixed during verification**:
  after adding the new `/alerts` backend endpoint, only the frontend
  container was rebuilt - the running backend container was still serving
  the pre-endpoint image, so the new route genuinely didn't exist yet
  live (a plain 404, not the app's own `CLOUD_ACCOUNT_NOT_FOUND` error).
  Caught by live browser verification, fixed by rebuilding and restarting
  the backend container, and re-verified live afterward that the
  endpoint (and the page section depending on it) now works correctly.
- Live scale verification: 60 cloud accounts created for one user via
  the real API (~1.4s total, confirming no backend-side slowdown even at
  that count); Dashboard load ~2.1s, Cloud Accounts page (60 rows,
  paginated) ~1.2s, pagination between pages smooth with no lag or
  freezing, zero crashes throughout.
- Live browser verification of the full restructured flow: sidebar shows
  only "Dashboard" for a non-admin user; the Recent alerts/recommendations
  panels are visible once the user has ≥1 cloud account; the new
  `/cloud-accounts/:id` page renders the account header, linked-
  deployments section, and active-alerts section correctly (including
  correct empty states for an account with nothing linked/no alerts).
  Zero console errors throughout. All test data (the scale-test user and
  its 60 accounts) deleted afterward.

## 5. Known Limitations (disclosed, not hidden)

- **60 accounts, not truly "unlimited," was what was actually tested.**
  This is a real, concrete number chosen to meaningfully exercise
  pagination and rendering, not an exhaustive stress test at, say,
  10,000 accounts - which was judged out of proportion for a dissertation
  project's verification standard, though nothing in the implementation
  (real SQL pagination, no client-side full-list loading) suggests it
  would behave qualitatively differently at a much larger count.
- **The per-account alerts feed shows only *active* alerts**, matching
  the platform-wide `/alerts` page's own default - acknowledged/resolved
  alert history for an account isn't shown on this page (it remains
  available via the platform-wide Alerts page's own status filter for
  users who still know that page's direct URL, even though it's no
  longer a sidebar link).
