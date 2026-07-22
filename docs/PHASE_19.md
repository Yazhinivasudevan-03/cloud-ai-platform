# Phase 19 — Production Hardening (Audit Roadmap, Part 2)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 19 (continuation of the "fix everything" audit roadmap work started in Phase 18)
Status: **In progress** - item 9 complete; items 10-13 continue in later sections of this document

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
