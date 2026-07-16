# Phase 7 — Frontend (React + TypeScript + Material UI)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 7 of ~10
Status: **Complete, with one disclosed verification gap (§9)**

---

## 1. Overview

Phase 7 gives the six backend phases built so far an actual UI: a React +
TypeScript single-page application covering authentication, the full
project→microservice→deployment→pod hierarchy, resource usage charts,
AI-model output (predictions/anomalies/failure risk), alerts, optimization
recommendations, cost forecasting, a notification center, and admin user
management. Two small backend endpoints were added first (global,
cross-deployment alert/recommendation listings) because the API as it stood
after Phase 6 only exposed per-deployment views, which would have made
several dashboard pages awkward or required inefficient client-side
aggregation.

## 2. Objectives Completed

- [x] Backend: `GET /api/v1/alerts` and `GET /api/v1/optimization-recommendations` (global, paginated, filterable, optional `deployment_id` filter) - 3 new tests, 120 total backend tests passing
- [x] Vite + React 18 + TypeScript scaffolded (not Create React App - see §3)
- [x] Material UI theme with light/dark mode (persisted to `localStorage`, respects OS preference on first visit)
- [x] JWT auth: axios interceptor attaches the access token to every request and transparently refreshes on `401` (single in-flight refresh, not one per failed request)
- [x] Full API service layer: one TypeScript module per backend router, fully typed against the backend's Pydantic schemas
- [x] Protected routing (`ProtectedRoute`) and role-gated routing (`RoleGuard`) using React Router v7
- [x] Pages: Login, Register, Dashboard, Projects (list/create/delete), Project detail (microservices + cloud costs + forecast), Microservice detail (deployments), **Deployment detail** (resource usage charts, LSTM predictions, anomaly/failure-risk tables, pods, alerts, optimization recommendations - the richest page), Alerts (global, with a Chart.js severity breakdown), Optimization (global), Notifications, Users (admin), Settings
- [x] Both named charting libraries genuinely used: Recharts for time-series (resource usage line charts) and Chart.js for the alerts severity-breakdown doughnut - not one token unused import
- [x] Reusable components (`DataTable`, `StatCard`, `PageHeader`, `StatusChip`, `ConfirmDialog`) so ~13 pages share one pagination/search/loading/empty-state implementation instead of each reinventing it
- [x] Dockerized: multi-stage build (Node → nginx), nginx reverse-proxies `/api/` to the backend so the browser never needs the backend's real address (no CORS in the containerized deployment)
- [x] Full live verification: real register/login/me flow through the actual nginx-proxied path, SPA deep-link routing, JS bundle serving - see §8
- [x] TypeScript build (`tsc -b && vite build`) passes with zero errors, both on the host and inside the Docker build

## 3. Technology Choices Beyond the Literal Spec

- **Vite instead of Create React App.** CRA is unmaintained (no updates since 2023, doesn't support current React/TypeScript tooling well). Vite is the current standard for a new React+TS SPA - faster dev server, faster builds, first-class TypeScript support.
- **`@tanstack/react-query` for server state.** Not in the original technology list, but it does exactly what "Live Metrics"/"Real-time Updates" needs: automatic refetching, cache invalidation on mutation, loading/error states - without hand-rolling all of that with raw `useEffect`+`useState` in every single page. Same category of judgment call as adding APScheduler in Phase 5.
- **MUI `Grid2` instead of legacy `Grid`.** MUI v6 (the current major version) kept the old item-based `Grid` API as default for backward compatibility and ships the new `size={{xs, md, ...}}` API as `Grid2`. This was actually caught as a real TypeScript error during the build (see §8) - not a stylistic choice made in advance, but the fix once the compiler pointed at it.
- **"Real-time" via polling, not WebSockets.** The backend has no WebSocket/SSE endpoint (out of scope for this project so far). The notification bell polls every 30s via React Query's `refetchInterval`. This is disclosed as a deliberate, honest simplification, not presented as true push-based real-time.

## 4. Folder Structure

```
frontend/
├── src/
│   ├── components/       # DataTable, StatCard, PageHeader, StatusChip, ConfirmDialog,
│   │                      # ErrorAlert, ProtectedRoute, RoleGuard, NotificationBell, UserMenu
│   ├── pages/              # One file per route (13 pages)
│   ├── services/            # httpClient.ts (axios + JWT) + one API module per backend router
│   ├── hooks/                # useDebouncedValue
│   ├── contexts/              # AuthContext, ThemeModeContext
│   ├── layouts/                 # AuthLayout (login/register), AppLayout (sidebar+topbar+content)
│   ├── types/                    # TypeScript types mirroring every backend Pydantic schema
│   ├── utils/                     # formatters, statusColors, chartSetup
│   ├── styles/                     # MUI theme factory (light/dark)
│   ├── App.tsx                       # route table
│   └── main.tsx                       # provider tree + entrypoint
├── Dockerfile                          # multi-stage: node build -> nginx serve
├── nginx.conf                            # SPA fallback + /api/ reverse proxy
└── vite.config.ts, tsconfig*.json, eslint.config.js
```

## 5. Explanation of Key Files

### `services/httpClient.ts`
The axios instance every API module shares. A request interceptor attaches
`Authorization: Bearer <token>`; a response interceptor catches `401`,
triggers exactly one in-flight refresh (concurrent failed requests all await
the same promise rather than each independently calling `/auth/refresh`),
retries the original request once with the new token, and on refresh
failure clears tokens and calls an app-registered `onAuthFailure` callback
(decoupled via a setter, avoiding a circular import between the HTTP client
and the auth context).

### `contexts/AuthContext.tsx`
Owns the current `User` and exposes `login`/`register`/`logout`/`hasRole`.
`hasRole(...)` checks `is_superuser` first (mirroring the backend's
`require_roles` dependency exactly), then the user's role list - the
frontend's RBAC logic is a direct reflection of Phase 2's backend logic, not
an independent reimplementation that could drift from it.

### `pages/DeploymentDetailPage.tsx`
The richest page: 6 tabs (Overview, Anomalies, Failure Risk, Pods, Alerts,
Optimization) covering resource usage line charts (Recharts), the latest
LSTM predictions with confidence scores, the Isolation Forest anomaly table,
the Random Forest failure-risk table, pod management, alert
acknowledge/resolve, and optimization recommendation apply/dismiss - every
Phase 3-6 backend capability surfaced in one place for a given deployment.

### `components/DataTable.tsx`
Generic paginated table (search box, loading spinner, empty state,
`TablePagination`) parameterized by a `DataTableColumn<T>[]` config - used by
every list page instead of each page implementing its own pagination
plumbing.

### `frontend/nginx.conf`
Two responsibilities: SPA fallback (`try_files $uri $uri/ /index.html` so
React Router handles deep links like `/deployments/3` after a hard refresh)
and reverse-proxying `/api/` to the backend container - verified live (see
§8) that the path rewrite is correct (`/api/v1/auth/login` →
`http://backend:8000/api/v1/auth/login`).

## 6. New Backend Endpoints (prerequisite for this phase)

### `GET /api/v1/alerts?deployment_id=&status=&severity=&page=&page_size=`
Same shape as the existing per-deployment listing, but `deployment_id` is now
an optional filter rather than a required path parameter - powers the
platform-wide Alerts page.

### `GET /api/v1/optimization-recommendations?deployment_id=&status=&recommendation_type=&page=&page_size=`
Same relationship to the existing per-deployment listing - powers the
platform-wide Optimization page.

Both reuse the exact same repository/service/controller pattern as every
other resource in this codebase (`search()` with `deployment_id: int | None`)
rather than introducing a parallel code path.

## 7. Environment Variables

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | frontend build arg | `/api/v1` (Docker) / `http://localhost:8000/api/v1` (local dev via `.env`) | Baked into the JS bundle at build time (Vite inlines `VITE_*` vars - there's no server-side runtime to read them from later) |

## 8. Verification Results

**Verified live:**
- `npm run build` (`tsc -b && vite build`) - zero TypeScript errors, production bundle built, both on the host and inside the Docker build stage
- `docker compose build frontend` - multi-stage image built successfully
- Full stack up (`mysql` + `backend` + `frontend`): all healthy
- `GET http://localhost:3000/` → `200`, correct HTML shell referencing the built JS bundle
- `GET http://localhost:3000/assets/index-*.js` → `200`, `application/javascript`, ~1.2MB matching the build output exactly
- SPA fallback routing: `GET /login` and `GET /deployments/3` (a deep link with no matching static file) both → `200` with the HTML shell, confirming nginx's `try_files` fallback works
- **Full auth flow through the actual nginx reverse proxy**: `POST http://localhost:3000/api/v1/auth/register` → `201`, `POST .../auth/login` → `200` with a real token pair, `GET .../auth/me` with that token → `200` with the correct user - proving the `/api/` → `backend:8000/api/` path rewrite is exactly correct, not just plausible
- Full backend test suite re-run after all Phase 7 changes: **120/120 passing**

**One real bug caught and fixed during this verification, not left for later:**
the initial `npm run build` failed with TypeScript errors on every `Grid`
usage with a `size` prop - MUI v6's default `Grid` export is the legacy
item-based API, not the new one. Fixed by importing `Grid` from
`@mui/material/Grid2` in the four files that use the `size` prop
(`DashboardPage`, `AlertsPage`, `ProjectDetailPage`, `DeploymentDetailPage`).
Also needed `@types/node` added as a dev dependency (`vite.config.ts` uses
`node:path` and `__dirname`, which aren't ambient without it).

## 9. Honest Disclosure: No Visual Browser Verification

This environment has **no headless browser tool available** - no
`chromium-cli`, no Chrome/Chromium binary, nothing the `run` skill's
browser-driven pattern could use. I checked explicitly (`Get-Command
chromium-cli`, `chromium`, `chrome` - none found) rather than assuming.

What this means concretely: I have **not** visually confirmed that the MUI
theme renders correctly, that the sidebar/topbar layout looks right, that
the Recharts/Chart.js charts actually paint, or that clicking through the
app in a real browser works pixel-for-pixel as intended. What I have
verified is everything in §8 - the build is clean, the bundle serves
correctly, the full authentication flow works end-to-end through the real
proxy, and the code was written and reviewed against the exact backend
contracts (types generated by hand against the actual Pydantic schemas, not
guessed). This is a materially weaker guarantee than actually looking at
the rendered page, and I'm not presenting it as equivalent. If you have a
browser handy, the fastest real check is: `docker compose up -d mysql
backend frontend`, then open `http://localhost:3000` and log in.

## 10. Known Limitations (disclosed, not hidden)

- **Bundle size**: the production JS bundle is ~1.2MB (368KB gzipped) in a single chunk - Vite warns about this. Code-splitting (`React.lazy` per route) would fix it; not done this phase to keep scope to what's verified.
- **No profile editing / password change**: the Settings page is read-only for profile info, because the backend has no `PATCH /auth/me` or change-password endpoint. Noted directly in the Settings page UI, not silently omitted.
- **Polling, not push, for "real-time"**: see §3.

## 11. Verification Checklist

- [x] `npm run build` passes with zero errors (host and Docker)
- [x] `docker compose build frontend` succeeds
- [x] Full stack (mysql+backend+frontend) starts healthy
- [x] Static assets serve correctly with correct content-type/size
- [x] SPA deep-link fallback routing works
- [x] Full register→login→me flow works through the real nginx proxy path
- [x] Backend test suite unaffected: 120/120 passing
- [ ] Visual browser rendering - **not verified, explicitly disclosed (§9)**

## 12. Next Phase Plan (Phase 8)

- Kubernetes manifests + Helm: namespace, deployments, services, ingress, secrets, configmaps, PV/PVC, HPA for every component built so far (backend, frontend, mysql, prometheus, grafana). This is also when `kube-state-metrics` (deferred since Phase 3) finally has a real cluster to introspect.

**Phase 8 will not start until this Phase 7 report is reviewed and confirmed.**

## 13. References

- Vite: https://vite.dev/guide/
- MUI Grid v2 migration: https://mui.com/material-ui/migration/upgrade-to-grid-v2/
- TanStack Query: https://tanstack.com/query/latest/docs/framework/react/overview
- React Router v7: https://reactrouter.com/
- Recharts: https://recharts.org/
- Chart.js: https://www.chartjs.org/docs/latest/
- nginx `try_files` / reverse proxy: https://nginx.org/en/docs/http/ngx_http_core_module.html#try_files
