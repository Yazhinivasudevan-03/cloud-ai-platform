# Phase 32 — Chromium Browser Extension (Manifest V3)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 32 (adds a second, independent client - a Manifest V3 browser extension - alongside the existing
React web app; the web app itself is unmodified)
Status: **Complete**

---

## 1. What this phase adds

A Chromium browser extension (`browser-extension/`) that works alongside the existing web app, not instead
of it: a popup dashboard, background polling with browser notifications, and a badge - all built entirely
on the backend's existing REST API and the existing JWT auth flow. No new backend endpoints, no new
backend business logic, and no changes anywhere under `frontend/`.

Works identically on **Chrome, Edge, Brave, and Opera** - all four are Chromium-based and implement the
same `chrome.*` extension APIs, so one Manifest V3 codebase covers all of them. See
[`docs/EXTENSION_INSTALL.md`](EXTENSION_INSTALL.md) for load-unpacked steps.

## 2. A note on "WebSocket connections"

The request's architecture section mentioned WebSocket. The backend has no WebSocket/SSE/push endpoint
anywhere - confirmed by grepping every router file and `main.py` before writing any extension code (zero
matches). The request's own fallback for the background service worker - "poll monitoring APIs if
required" - already anticipated this. This phase implements polling only, via `chrome.alarms` (the
correct Manifest V3 mechanism; `setInterval` does not survive service-worker suspension, so it would
silently stop working after the browser reclaims the idle worker). Real backend push is a reasonable
future phase, not built or faked here.

## 3. Design decision: no client-side threshold math

The backend's `AlertEvaluationService` already evaluates every category the request lists - CPU/memory/
disk/network tiers (elevated/high/saturated), cost thresholds, node failure, pod restart, container
failure, and resource-optimization recommendations - and writes them all to the same `Alert` stream
(Phases 21/23). The extension never recomputes any of this. It polls `GET /alerts?status=active` and
diffs alert IDs against the previous poll to decide what's "new." This keeps the extension a thin client
instead of a second, potentially-inconsistent alerting engine.

## 4. Endpoints reused (all pre-existing, all under `/api/v1`)

| Purpose | Endpoint |
|---|---|
| Login | `POST /auth/login` (form-encoded, same wire format the web app uses) |
| Token refresh | `POST /auth/refresh?refresh_token=...` |
| Connected cloud accounts | `GET /cloud-provider-accounts` |
| Real-time usage (CPU/mem/disk/network) | `GET /cloud-provider-accounts/{id}/deployments` (`latest_usage` is already embedded per deployment) |
| Active / critical alerts, badge | `GET /alerts?status=active` |
| AI recommendations | `GET /optimization-recommendations?status=pending` |
| Cloud cost | `GET /projects` + `GET /projects/{id}/cloud-costs?since=<1st of month>`, summed client-side (no per-account cost field exists in this schema - cost is project-scoped, same as the web app's own `DashboardPage.tsx`, which does the identical client-side fan-out because no backend aggregation endpoint exists either) |
| Notification history link | `GET /notifications/summary` |

No dashboard-aggregation endpoint exists anywhere in the backend - confirmed by reading
`frontend/src/pages/DashboardPage.tsx`, which fans out the same kind of parallel calls and combines them
client-side. The extension follows the same, already-established pattern rather than inventing a new one.

## 5. A real, pre-existing bug found and fixed

Live-verifying the extension against a real account surfaced a genuine backend bug, unrelated to any
extension code: `CloudAccountDeploymentSummary.cloud_resource_identifier` was declared as a required
`str` in `backend/app/schemas/cloud_provider_account.py`, but the underlying `Deployment.cloud_resource_identifier`
column - and `DeploymentCreate.cloud_resource_identifier` - are genuinely optional (`str | None`). Any
deployment that exists before being linked to a synced cloud resource crashed
`GET /cloud-provider-accounts/{id}/deployments` with a 500 (a Pydantic response-validation failure). This
endpoint is the same one the *existing* web app's Cloud Accounts "at a glance" usage view already calls,
so this was a latent bug there too, not something introduced by this phase - the extension's real-data
verification just happened to be the first thing that hit the null case. Fixed by widening the schema
field to `str | None = None` (one line, additive, no other behavior changed).

A minor, purely cosmetic frontend counterpart of the same root cause exists (`frontend/src/types/index.ts`
declares the same field as non-optional `string`, so a null value would render as literal "null" text in
one label on `CloudAccountDetailPage.tsx` rather than crashing anything) - deliberately **not** touched in
this phase, per the explicit instruction to keep the existing web app unchanged. Disclosed here instead of
silently fixed or silently ignored.

## 6. Badge and notifications (requirement 8 / requirement 4)

- Badge: red + the critical count when any critical alert is active; otherwise yellow + the warning
  count; otherwise cleared. Uses `chrome.action.setBadgeText`/`setBadgeBackgroundColor`.
- New alert IDs (not seen on the previous poll) fire a real `chrome.notifications.create()`, using the
  alert's own `alert_type`/`severity`/`message` - this already covers every category the request lists,
  since they're all just `alert_type` values in the same existing stream. Clicking a notification opens
  the corresponding web app page (`/alerts` for most types, `/optimization` for resource-optimization
  recommendations) via `chrome.tabs.create`.
- The first poll after login seeds the "already seen" set without firing notifications, so existing
  alerts from before install don't cause a notification flood.
- **Notification sound**: Manifest V3's `chrome.notifications` API has no explicit mute/sound toggle.
  The closest real, documented lever is notification `priority` (0-2) - the Settings "Notification sound"
  toggle lowers priority to 0 when disabled instead of the severity-based 1/2. This is disclosed here as
  a best-effort mapping onto a real API capability, not a guaranteed mute - full sound behavior is at the
  OS/browser's discretion either way.

## 7. Files

New: `browser-extension/` (manifest, background service worker, popup UI - login/dashboard/settings
views, shared auth/storage/api-client/dashboard-data modules, generated placeholder icons, Vite build
config), `docs/EXTENSION_INSTALL.md`, `docs/images/phase32-extension-dashboard.png`.

Modified: `backend/app/schemas/cloud_provider_account.py` (the one-line bug fix above), `.gitignore`
(`browser-extension/dist/`), `README.md`.

Not modified: anything under `frontend/` - the existing web app is unchanged, confirmed via `git status`
before committing.

## 8. Live verification

Built the extension (`npm run build`), loaded the real unpacked `dist/` into a genuine Chromium instance
via Playwright (`launchPersistentContext` with `--load-extension`, not a mock), and drove it against the
**real, running** backend and MySQL - not stubbed:

- Created a real user, cloud provider account, project/microservice/deployment, and one real breaching
  CPU reading (96%) via the platform's own `ResourceUsage` model, then ran the platform's own real
  `AlertEvaluationService.evaluate_all()` - the exact code path the live scheduler runs - producing a
  genuine `Alert` row, not a hand-inserted fake one.
- Logged into the extension's real login form with real credentials against the real `/auth/login`
  endpoint.
- Confirmed the dashboard rendered real data: 1 connected account (`ext-verify-account`, AWS,
  us-east-1), "Needs attention" health badge (correct - credentials were never validated for this
  throwaway account), 1 active / 1 critical alert, real resource usage (CPU 96.0%, Memory 512 MB, Disk
  1.0 GB, Network 200 Kbps), "No billing entries this month" and "No pending recommendations" (both
  correctly empty for a fresh account).
- Confirmed the Settings view opens and returns to the dashboard correctly.
- Clicked the real "Refresh monitoring" quick action (the same message-passing path a real user
  triggers) and confirmed, via the live service worker's own state: the badge updated to `"1"` with
  background color `#d32f2f` (red - matches the critical-badge requirement exactly), a real
  `chrome.notifications.create()` fired for the new alert, and the click-target mapping correctly
  recorded `/alerts` as the page it would open.
- Screenshot of the live-rendered popup: `docs/images/phase32-extension-dashboard.png`.
- All throwaway rows (user, account, project, microservice, deployment, resource usage, alert) were
  deleted afterward - nothing left behind in the real database.
- Confirmed the existing web app is untouched: `git status` before committing shows zero changes under
  `frontend/`.

## 9. Testing

`browser-extension`: `npm run build` runs a strict TypeScript check (`tsc --noEmit`, `strict: true`,
`noUnusedLocals`/`noUnusedParameters`) before bundling - zero errors. No existing backend/frontend test
suite needed changes, since nothing under `backend/app` changed except the one-line schema widening
(additive, backward compatible - existing tests for that endpoint continue to pass unchanged).
