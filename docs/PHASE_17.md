# Phase 17 — Reliability Polish (Audit Roadmap Item 14)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 17 (post-completion feature addition, beyond the original 10-phase plan)
Status: **Complete and verified**

---

## 1. Overview

Requested directly as "fix 14," referring to the lowest-priority, bundled
item on the technical audit's prioritized roadmap: *"VPA support,
retry/backoff on external calls, scaling cooldown periods, safety-limit
guardrails on recommendations — polish items that improve robustness
without being blocking for either dissertation submission or a first real
deployment."* This phase implements all four.

## 2. What Was Built

### VerticalPodAutoscaler manifest (recommendation-only)
`kubernetes/base/backend-vpa.yaml` and the equivalent Helm template
(`templates/backend-vpa.yaml`, gated by `backend.vpa.enabled`, default
`false`). Deliberately **not** added to `kustomization.yaml`'s resource
list, for the same reason `ml-models-job.yaml`/`ml-models-cronjob.yaml`
already aren't: unlike the HPA, VerticalPodAutoscaler is not a built-in
Kubernetes API - it requires the VPA controller/CRDs to be installed
separately, and bundling it into the default `kubectl apply -k` would fail
outright with an "unknown kind" error on any cluster without that
controller, including the Docker Desktop cluster this project verified
Phase 8's manifests against.

`updateMode: "Off"` (recommendation-only) is deliberate, not a placeholder:
an "Auto" VPA that evicts and recreates pods to apply new resource
requests would fight the existing HPA over the same cpu/memory metric on
the same Deployment - a documented anti-pattern. "Off" surfaces the same
right-sizing recommendations via `kubectl describe vpa backend-vpa`
without ever taking scaling action itself.

### Retry/backoff on external calls
A shared `app/utils/retry.py` plus one CloudWatch-specific predicate in
`aws_cloudwatch.py`, all built on `tenacity`. Every retry policy is
deliberately narrow - it only retries failure modes that are actually
transient:

- **CloudWatch** (`aws_cloudwatch.py`): retries `Throttling`,
  `RequestLimitExceeded`, `ServiceUnavailable`, and similar AWS error
  codes, plus connection-level `BotoCoreError`s. A non-transient rejection
  (bad credentials, `InvalidClientTokenId`) still fails on the very first
  attempt, exactly as before - retrying a config error 3 times would only
  waste time before failing anyway.
- **Slack/Telegram** (`http_retry`): retries connection-level
  `httpx.TransportError` and 5xx responses. A 4xx (bad webhook URL, bad
  bot token) is a config error and is not retried.
- **Email** (`smtp_retry`): retries generic `smtplib.SMTPException`/
  `OSError`, but explicitly excludes `SMTPAuthenticationError` and
  `SMTPRecipientsRefused` - both permanent, not transient.

After retries are exhausted, every notifier now catches the final
exception, logs it, and returns `False` - the same contract as the
existing "not configured" fallback - rather than letting the exception
propagate. This closes a real reliability gap the audit didn't originally
name but found during implementation: previously, a single flaky Slack
webhook or SMTP server could raise an uncaught exception all the way up
through `AlertEvaluationService`, crashing the *entire* scheduled alert
evaluation run for every deployment, not just failing to deliver one
notification.

### Recommendation cooldown period
`OPTIMIZATION_RECOMMENDATION_COOLDOWN_MINUTES` (default 60, matching the
evaluation interval). `OptimizationRecommendationRepository.get_recently_resolved()`
checks whether a recommendation of the same type was dismissed or applied
within the cooldown window; if so, `OptimizationService` skips recreating
it even if the triggering condition still holds. Previously, dismissing a
recommendation had no effect on the very next scheduled evaluation run -
if the condition (e.g. sustained high CPU) was still present, the exact
same recommendation reappeared immediately, defeating the point of
dismissing it. This mirrors the stabilization-window concept real
Kubernetes HPAs use for the same reason: prevent thrashing.

### Safety-limit guardrail on `scale_deployment`
`recommendation_engine.py`'s HPA-style formula
(`desiredReplicas = ceil(currentReplicas × currentUtilization / targetUtilization)`)
previously had a floor (`max(1, ...)`) but no ceiling - a large enough CPU
reading could recommend scaling to an arbitrarily high replica count. It
now clamps to `OPTIMIZATION_MAX_SCALE_REPLICAS`, the same practical
scaling ceiling the `increase_pods`/`increase_cpu` branch immediately
above it already respects, so a runaway CPU spike can no longer produce a
recommendation to scale to an unbounded replica count.

## 3. Verification Results

- Backend test suite: **179/179 passing** (169 existing + 10 new): 2 for
  the cooldown period (suppressed within the window, recreated once it
  expires), 1 for the `scale_deployment` replica cap, 5 for notifier
  retry/backoff (Slack retries-then-succeeds, exhausts-then-degrades,
  doesn't retry a 4xx; email retries-then-succeeds, doesn't retry an auth
  failure), 2 for CloudWatch retry/backoff (retries a `Throttling`
  response then succeeds, doesn't retry `InvalidClientTokenId`).
- `kubectl kustomize kubernetes/base` still builds cleanly with the new
  VPA manifest correctly excluded from the default resource set.
- `helm template`/`helm lint` confirm the Helm VPA template renders
  correctly when explicitly enabled (`--set backend.vpa.enabled=true`)
  and renders as an empty (comment-only) document by default, matching
  the existing HPA template's own guard pattern.
- The live Kubernetes cluster used for Phase 8's original live
  verification was not running during this phase - the VPA manifests are
  therefore verified by template rendering and `kubectl kustomize`/`helm
  lint` only, not by a live `kubectl apply` against a cluster with the
  VPA controller installed. This is disclosed rather than assumed.

## 4. Known Limitations (disclosed, not hidden)

- **VPA manifests are schema/template-validated, not live-applied.** No
  VPA controller was available in this environment to confirm the
  resource is actually accepted and produces recommendations against a
  real cluster.
- **The cooldown is per-recommendation-type, not per-deployment overall.**
  A deployment triggering two different recommendation types (e.g.
  `increase_pods` and `increase_memory`) at once tracks each type's
  cooldown independently, which is the intended, finer-grained behavior,
  not a limitation - noted here only so it isn't mistaken for one.
