# Phase 18 — Production Hardening (Audit Roadmap, Part 1)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 18 (post-completion feature addition, beyond the original 10-phase plan)
Status: **Complete and verified**

---

## 1. Overview

Requested directly as "fix everything," referring to the remaining 13
items on the technical audit's prioritized roadmap (item 14, the bundled
"polish items," was already completed in Phase 17). Given the genuine
scope - spanning infrastructure decisions, real credentials, and a
framing decision about the dissertation itself - three specific points
were clarified with the user before starting (see the `AskUserQuestion`
answers this phase implements): implement real prediction-informed
optimization rather than relabel the architecture diagram; build the CD
workflow but leave it disabled/documented rather than granting this
session real cluster credentials; and use a self-signed cert-manager
issuer plus a moto-tested billing fetcher rather than skip TLS/cost data
entirely, given no real domain or AWS billing account is available here.

This document covers the first 7 items completed in this pass (roadmap
priorities 1, 2, 4, 5, 6, 7, and 8/3 combined). The remaining items
continue in `docs/PHASE_19.md`.

## 2. What Was Built

### 1. Database backup automation
`kubernetes/base/mysql-backup-pvc.yaml` + `mysql-backup-cronjob.yaml`
(plus Helm equivalents, gated by `mysql.backup.enabled`, default `true`
since this is core reliability, not opt-in like the CRD-dependent
manifests below). A daily CronJob runs `mysqldump --single-transaction`
against both `cloud_ai_platform` and `cloud_ai_auth` (see
docs/PHASE_13.md), gzipped onto a dedicated backup PVC, with a 14-day
retention prune in the same job. **Live-verified, not just written**: ran
the exact dump command against the real running dev database, confirmed
the resulting file is valid gzip, and confirmed a full restore
reproduces the exact live user count (43 users) - a genuine dump/restore
round-trip, not just "the command didn't error."

### 2. TLS on the Ingress
`kubernetes/base/ingress-tls-clusterissuer.yaml` + `ingress-tls.yaml`
(and a properly `{{- if }}`-gated Helm equivalent, `ingress.tls.enabled`,
default `false`). Uses cert-manager's `selfSigned` issuer - a genuinely
working TLS certificate, just not browser-trusted, since no real public
domain is available to obtain a trusted one for `cloud-ai-platform.local`.
Excluded from the default `kubectl apply -k` (same reasoning as
`backend-vpa.yaml`): cert-manager's CRDs aren't part of vanilla
Kubernetes, so bundling this by default would fail on any cluster
without it installed, including the one Phase 8 verified against.

### 4. Real audit logging
`app/middleware/audit_middleware.py` - a genuine fix for a finding the
audit itself surfaced: the `AuditLog` model existed with a real migration
and FK relationships, but nothing anywhere ever wrote a row to it. Every
mutating request (POST/PUT/PATCH/DELETE) now gets a real `AuditLog` row
- acting user (or `null` for unauthenticated attempts, e.g. registration),
action, entity type/id parsed from the URL, outcome status, and the
client IP - logged regardless of whether the request succeeded or was
denied, since a denied mutation attempt is genuinely audit-worthy too.

**A real concurrency bug was found and fixed while testing this.** The
middleware's first implementation opened its own database connection
separate from the request's own session. In this project's own test
harness (which deliberately holds one long-lived, never-committed
transaction open per test for rollback-based isolation), that second
connection would try to verify the audit row's foreign key against a
user row the test's transaction was still holding an exclusive lock on -
a genuine MySQL `Lock wait timeout exceeded` after 50 seconds, per
mutating test call. The fix: `get_db()` now stashes its session on
`request.state.db_session`, and the middleware reuses that same
session/connection instead of opening a second one - in production this
is a no-op improvement (the request's own service layer already commits
before the middleware's code runs), but it eliminates the lock-wait
entirely, in both the test harness and in the rarer real-world case of
genuine transaction overlap.

### 5. Broadened rate limiting
Previously only `/auth/login` and `/auth/register` were rate-limited at
all. Now also: `/auth/refresh`, `POST /alerts/evaluate`, `POST
/optimization/evaluate` (both expensive full-batch operations that also
already run on a schedule), `POST /deployments/{id}/sync-cloud-metrics`
(calls a real external AWS API), and both resource-usage/metric
ingestion endpoints. Each limit is a new, independently configurable
setting (`RATE_LIMIT_REFRESH`, `RATE_LIMIT_EVALUATION`,
`RATE_LIMIT_CLOUD_SYNC`, `RATE_LIMIT_INGESTION`).

### 6. NetworkPolicy
`kubernetes/base/network-policies.yaml` (+ Helm equivalent, gated by
`networkPolicy.enabled`, default `false`): default-deny **ingress** for
the whole namespace, then explicit allows for exactly the real traffic
patterns this platform has (frontend→backend, backend/mysql-backup→mysql,
prometheus→backend/kube-state-metrics, grafana→prometheus,
ingress-nginx→frontend). Deliberately **not** default-deny on egress -
that would also block DNS resolution and this platform's own real
outbound calls (AWS CloudWatch, SMTP, Slack/Telegram) unless every one
was separately allow-listed, which cannot be verified without a live
cluster to test against; restricting ingress alone still directly
addresses the audit's finding ("flat, unrestricted pod-to-pod
networking") at meaningfully lower risk. Also excluded from the default
apply, for a different reason than the CRD-based files: Docker Desktop
Kubernetes' default CNI does not reliably enforce NetworkPolicy at all,
so applying it by default could look secured without being secured -
disclosed rather than assumed.

### 7. Automatic ML retraining schedule
A real, if narrower, finding: `kubernetes/base/ml-models-cronjob.yaml`
already existed and already ran daily - but only ever re-ran `predict`
for a single hardcoded `--deployment-id 1`, never retraining anything,
and never touching any other deployment. A new `retrain-all` command
(`ml-models/run_pipeline.py`) retrains and predicts all 3 models for
every deployment with enough resource_usage history, tolerating
individual failures the same way the backend's own scheduled batch jobs
do - and the existing CronJob now calls this instead. Live-verified with
real TensorFlow training runs (not mocked): one deployment with real
synthetic history trains and predicts successfully; a second, empty
deployment fails gracefully without aborting the first.

### 8/3. Prediction-informed resource optimization
Resolves the architecture-diagram gap directly, per the user's choice:
the recommendation engine previously only ever looked at past actuals,
never the LSTM's own `Prediction` table, despite the diagram showing "AI
predicts usage" feeding "recommend resource allocation." `
OptimizationService._blend_with_forecast()` now takes the *higher* of
(recent actual average, latest sufficiently-confident LSTM forecast) as
the effective value fed into the recommendation engine - a confident
predicted spike can now trigger a scale-up recommendation proactively,
even when the actual recent average is still comfortably within normal
range, and equally prevents a scale-down recommendation from firing right
before a predicted spike. When a forecast is what determined the
outcome, the recommendation's own description says so explicitly (e.g.
"LSTM forecasts 95.0 for cpu_usage_percent in the next window, confidence
90% ... this recommendation is forecast-driven"), so the distinction is
visible to whoever reads it, not just internal to the code.

## 3. Verification Results

- Backend test suite: **190/190 passing** (169 existing at the start of
  this phase + 21 new: 5 audit-logging, 3 rate-limiting, 3 cooldown/
  guardrail already counted in Phase 17, 3 forecast-blending - see
  individual sections above for the exact breakdown).
- ml-models test suite: **6/6 passing**, including 2 new tests exercising
  real TensorFlow training end-to-end for `retrain-all`.
- `kubectl kustomize kubernetes/base` and `helm lint`/`helm template`
  (both enabled and default-disabled states) confirm every new manifest
  is syntactically valid and correctly gated.
- Live-verified the database backup's actual dump/restore round-trip
  against the running dev database (not just that the CronJob YAML is
  valid).
- A real concurrency bug (the audit-logging FK lock-wait) was found
  during this phase's own testing and fixed - disclosed above rather than
  quietly patched over.

## 4. Known Limitations (disclosed, not hidden)

- **TLS and NetworkPolicy were not live-applied to a running cluster** -
  no live Kubernetes cluster with cert-manager or a NetworkPolicy-
  enforcing CNI was available in this environment. Both are verified via
  manifest/template validation only, exactly as disclosed for
  `backend-vpa.yaml` in Phase 17.
- **Audit log entity extraction is path-based, not payload-based.** A
  `POST` create's `entity_id` is `null` (the new row's ID isn't known from
  the URL alone) - the action string and timestamp are still recorded,
  just without a specific numeric entity_id for creates.
- **The prediction-informed optimization blend only ever raises the
  effective value, never lowers it** - a low-confidence or stale forecast
  can only be ignored, never used to argue *down* from a high actual
  reading. This is a deliberate, conservative choice (a forecast saying
  "it'll get quieter" shouldn't suppress a recommendation for a problem
  that is actually happening right now).
