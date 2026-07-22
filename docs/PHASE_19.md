# Phase 19 — Production Hardening (Audit Roadmap, Part 2)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 19 (continuation of the "fix everything" audit roadmap work started in Phase 18)
Status: **In progress** - items 9, 10 complete; items 11-13 continue in later sections of this document

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
