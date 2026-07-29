# Phase 25 — Dynamic Multi-Cloud Region Discovery, Resource Inventory & Provisioning

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 25 (extend every connected cloud account with live, provider-discovered region lists in place of
any hardcoded region data; a full read-only resource inventory; and real deploy/destroy provisioning for
compute/storage/networking — across all 5 supported providers: AWS, Azure, GCP, Oracle Cloud, Alibaba Cloud)
Status: **Complete**

---

## 1. Overview

This is the largest single feature in the project's history — comparable to several previous phases
combined — and was deliberately broken into six independently-committed, independently-tested
sub-phases (25A–25F), each stopped and confirmed with the user before the next began, per this
project's established phase-by-phase workflow discipline.

1. **25A — Region discovery foundation.** A provider-agnostic `CloudProviderClient` interface and a
   `provider_factory` registry (adding a 6th provider is registering one adapter class, never touching
   a controller/service/router), real `list_regions()` for AWS/Azure/GCP, a background sync job plus an
   on-demand refresh, and a frontend region switcher with an "All Regions" aggregate mode.
2. **25B — Oracle Cloud + Alibaba Cloud integrations.** Both providers previously had zero backend
   integration (UI-only "connect" buttons from Phase 24) — built from scratch against their official
   SDKs (`oci`, `alibabacloud_*`/`oss2`), registered in the same factory with zero changes to any
   existing endpoint/service/frontend code.
3. **25C — Read-only resource inventory.** Compute/clusters/databases/storage/networking, real for all
   5 providers (25 read paths), one generic endpoint dispatching by category, with an "all regions"
   aggregation mode that tolerates individual region failures without blanking the rest.
4. **25D — Provisioning.** Real `deploy()`/`destroy()` for compute instances, storage buckets, and basic
   networking (15 deploy + 15 destroy paths), hard-capped to one fixed smallest/free-tier instance size
   per provider, gated by a confirm-to-destroy flow and a full audit trail for every attempt.
5. **25E — Polish.** A richer error taxonomy for region discovery, retry consistency extended to every
   resource-listing call, a real TTL gate on the region cache, and "All Regions" as the default for an
   account created without an explicit region.
6. **25F (this document) — Full regression, live verification, docs, final commit.**

Every new integration follows this project's already-established pattern: a typed credentials dict,
`tenacity` retry on transient errors only, a `ValidationAppError` with a specific `code` on real
failures, and honest disclosure of any real limitation (e.g. GCP's globally-scoped VPC networks, S3's
account-wide `ListBuckets`) rather than a fabricated per-provider workaround.

## 2. Database schema changes

One additive migration (`ee6aa282de29`), no destructive changes:

- `cloud_provider_accounts.available_regions` — `TEXT NOT NULL DEFAULT '[]'`, a JSON-encoded list of
  `{id, display_name}` pairs discovered from the provider's own API.
- `cloud_provider_accounts.last_region_sync` — nullable `DATETIME`, when the above was last populated by
  a real live call.
- `cloud_provider_accounts.connection_status` — `VARCHAR NOT NULL DEFAULT 'CONNECTED'`, set to `ERROR`
  by a failed sync attempt.
- `cloud_provider_accounts.region`'s existing meaning is unchanged in type — it becomes "currently
  selected region for this account's requests" (accepting the literal `"all"` sentinel) with no rename
  needed; every pre-existing caller (`CloudSyncService`, `CloudCostService`, etc.) kept working
  untouched throughout all six sub-phases.

No schema change was needed for OCI/Alibaba credentials — `credentials_encrypted` already stores an
arbitrary encrypted key/value dict (OCI's config-style `user`/`tenancy`/`fingerprint`/`key_content`;
Alibaba's `access_key_id`/`access_key_secret`) — and `AuditLog` (Phase 15) was reused as-is for the new
provisioning audit trail (see §5).

## 3. Cross-cutting architecture

- **`app/integrations/cloud_provider_client.py`** — an abstract `CloudProviderClient` with the full
  method surface added across all six sub-phases: `list_regions`, `refresh_regions`, `list_projects`,
  `list_resources`/`list_clusters`/`list_databases`/`list_storage`/`list_networking`, `list_monitoring`,
  `list_costs`, `deploy`, `destroy`. A method not yet implemented for a given provider raises a clear
  `ValidationAppError` naming exactly what's missing (`_not_yet_supported`), never a silent empty result.
- **`app/integrations/provider_factory.py`** — `get_cloud_provider_client(provider, credentials, region)`,
  backed by a plain registry dict. This is the *only* place a provider is ever registered; no
  controller/service/router file branches on provider name anywhere in Phase 25.
- **`app/integrations/providers/`** — one adapter class per provider (`aws_provider.py`,
  `azure_provider.py`, `gcp_provider.py`, `oci_provider.py`, `alibaba_provider.py`), each wrapping the
  already-real monitoring/cost fetchers from earlier phases for `list_monitoring`/`list_costs` rather
  than duplicating that logic.
- **`CloudResourceSummary`** (`TypedDict`) — the one normalized shape every `list_*`/`deploy` method
  returns: `{id, name, type, region, status, created_at}`. Provider-specific fields that don't fit are
  omitted, never invented.

## 4. Region discovery, caching, and the "All Regions" mode

- `list_regions()` is a real, live call to each provider's own API — never a hardcoded list: AWS
  `ec2.DescribeRegions`, Azure `SubscriptionClient.subscriptions.list_locations`, GCP
  `compute_v1.RegionsClient`, OCI `IdentityClient.list_region_subscriptions`, Alibaba ECS
  `DescribeRegions`.
- **`CloudRegionSyncService`** — `sync_account()` (raises on failure, used by the on-demand refresh path
  and a first-ever read) and `sync_all_regions()` (tolerates individual account failures, used by the
  scheduled job, `CLOUD_REGION_SYNC_INTERVAL_HOURS`, default 24h). A newly-discovered region past the
  account's first-ever sync dispatches a `new_cloud_regions_available` notification through the existing
  fan-out.
- **TTL cache gate (25E)** — `GET .../regions` serves the stored snapshot as-is while
  `last_region_sync` is within `CLOUD_REGION_CACHE_TTL_HOURS` (default 24h, additive setting); a
  snapshot older than that — or an account never synced at all — triggers one live call first.
  "Refresh Regions" always bypasses this and forces a live call regardless of age. The setting itself
  existed since 25A but was only actually wired into the read path in 25E.
- **"All Regions" (25E)** — a new `CloudProviderAccount` created without an explicit `region` field now
  defaults to `"all"` (`ALL_REGIONS_SENTINEL`), the platform's own aggregate-view sentinel, rather than
  forcing a specific pick up front. This platform's own "Connect Cloud Account" UI always supplies a
  concrete region (for its region+timezone auto-association flow, see Phase 22), so this only changes
  the default for a caller — e.g. a future non-UI API consumer — that omits it.

## 5. Resource inventory & provisioning

- **Read-only inventory (25C)** — `GET /cloud-provider-accounts/{id}/resources?category=&region=`, one
  endpoint dispatching to the right adapter method by category
  (compute/clusters/databases/storage/networking); `region=all` aggregates across every discovered
  region in the service layer, tolerating individual region failures.
- **Provisioning (25D)** — `POST .../resources/deploy` / `DELETE .../resources/{type}/{id}`, for
  compute/storage/networking only (clusters/databases stay read-only in this pass). Compute `deploy()`
  is hard-capped to one fixed, smallest/free-tier-eligible instance size per provider —
  `t3.micro` (AWS) / `Standard_B1s` (Azure) / `e2-micro` (GCP) / `VM.Standard.E2.1.Micro` (OCI) /
  `ecs.t5-lc1m1.small` (Alibaba) — not user-configurable in this pass, to bound real-world
  cost/blast-radius risk from the very first release of a platform capability with genuine real-world
  side effects.
- **Confirm-to-destroy** — the `DELETE` request body's `confirm` field must exactly equal the
  `resource_id` already in the URL path (the same value the frontend already displays); a mismatch is a
  `422 DESTROY_CONFIRMATION_MISMATCH` — a validation failure, not an authorization one.
- **Audit trail** — `app/services/cloud_provisioning_service.py` writes one `AuditLog` row for *every*
  deploy/destroy attempt, success or failure (`action="cloud_resource_deploy"` /
  `"cloud_resource_destroy"`, `entity_type=resource_type`). `AuditLog` (Phase 15) was reused as-is rather
  than adding a new model: `entity_id` stays `None` since it's an `Integer` column but cloud resource
  IDs (ARNs/OCIDs/instance IDs) are strings — the real identifier and outcome live in the JSON `details`
  field instead (`{provider, cloud_provider_account_id, region, resource_type, resource_id, outcome}`).
- **Storage destroy relies on the provider's own empty-bucket precondition** (S3/OSS/Azure
  Storage/GCS all reject deleting a non-empty bucket) rather than force-emptying it first — a genuine
  safety feature, not a bug to route around.
- **Honest prerequisite disclosure** — every provider's compute `deploy()` requires real, pre-existing
  infrastructure this platform cannot fabricate (an AMI id, an Azure resource group + subnet + admin
  credentials, a GCP image path, an OCI availability domain + subnet, an Alibaba security group).
  Missing fields raise a `*_DEPLOY_SPEC_INCOMPLETE` error naming exactly what's missing.

## 6. Error taxonomy & retry consistency (25E)

- **Region discovery** (the one path called for every account, every TTL cycle) gained a richer error
  taxonomy: distinct `ValidationAppError` codes for credentials expired, credentials rejected, access
  denied, throttled (after retries exhausted), provider outage, timeout, network unreachable, and
  no-regions-returned — each derived from a real distinction the provider's own SDK actually exposes
  (AWS `Error.Code`, Azure/OCI HTTP status, GCP `google.api_core.exceptions` classes, Alibaba
  `TeaException.code`), never a fabricated guess. Where an SDK genuinely can't tell two scenarios apart
  (e.g. Azure's `ClientAuthenticationError` never distinguishes "expired" from "otherwise invalid"), both
  fold into one honestly-named category rather than inventing a false split.
- Resource-inventory/deploy/destroy paths keep their existing single code-per-operation (e.g.
  `AWS_DEPLOY_FAILED`) unchanged — that already identifies which operation failed, and rewriting ~50
  already-tested codes for cosmetic uniformity wasn't worth the regression risk.
- **Retry consistency** — every provider's `tenacity` retry decorator (previously wired to
  `list_regions()` only) now also wraps `list_resources`/`list_clusters`/`list_databases`/
  `list_storage`/`list_networking`'s real SDK calls, across all 5 providers.
- **Deploy/destroy deliberately do NOT get automatic retry.** Retrying a non-idempotent create/delete
  call after a transient network blip risks silently double-provisioning a real, billable resource, or
  masking a race — a genuine blast-radius concern, not an oversight, consistent with 25D's
  fixed-instance-size cap and confirm-to-destroy gate.

## 7. New/changed API surface

| Endpoint | Change |
|---|---|
| `GET /cloud-provider-accounts/{id}/regions` | New (25A) — TTL-gated live/cached region list (25E) |
| `POST /cloud-provider-accounts/{id}/refresh-regions` | New (25A) — always bypasses the cache |
| `PATCH /cloud-provider-accounts/{id}/region` | New (25A) — switch region, accepts `"all"` |
| `GET /cloud-provider-accounts/{id}/resources` | New (25C) — `category`/`region` query params |
| `POST /cloud-provider-accounts/{id}/resources/deploy` | New (25D) |
| `DELETE /cloud-provider-accounts/{id}/resources/{type}/{id}` | New (25D) — confirm-to-destroy body |
| `POST /cloud-provider-accounts` | `region` now optional, defaults to `"all"` (25E) |

## 8. Frontend changes

- Region dropdown (25A) — real, live-populated, never hardcoded; loading/refreshing/switching states;
  an "All Regions" option; switching invalidates every query already scoped by
  `cloud_provider_account_id` (the Phase 24 account switcher).
- `CloudAccountResourcesCard` (25C) — a tabbed Compute/Clusters/Databases/Storage/Networking view with
  its own region selector and per-tab loading/empty/error state.
- `DeployResourceDialog` / `DestroyResourceDialog` (25D) — a "Deploy resource" dialog (type/region/name +
  an optional provider-specific spec key/value editor for prerequisites like an AMI id or Azure resource
  group) and a destroy confirmation dialog requiring the resource's own ID typed in, with an explicit
  irreversible-action warning — wired only into the Compute/Storage/Networking tabs (Clusters/Databases
  stay read-only, matching the backend).

## 9. Known, disclosed limitations

- **OCI and Alibaba Cloud have no available emulator** (unlike AWS's `moto`) and no live account was
  available to validate against in this environment — both adapters are verified only against mocked
  SDK client responses (`test_oci_provider.py`, `test_alibaba_provider.py`, and their respective
  provisioning test files), the same disclosed caveat this project already applies to Azure/GCP
  monitoring (Phase 24).
- **GCP Compute Engine instances are zone-scoped, not region-scoped** — `deploy()`/`destroy()` assume the
  same `f"{region}-a"` default zone; an instance created in a non-default zone within that region can't
  be destroyed via this same-zone-guessing path without the caller tracking its real zone separately.
- **AWS S3's `ListBuckets` is account-wide, not region-scoped** — a bucket created in a different region
  still appears in every region's storage inventory (a real S3 API limitation, not a filtering bug).
- **GCP VPC networks are global, not regional** — `list_networking()` returns the same result regardless
  of which region was requested, disclosed rather than fabricating a per-region filter GCP's own API has
  no concept of.
- **Full taxonomy scoped to region discovery only** — the richer 8-category error classification (25E)
  applies to `list_regions()`; resource-inventory/deploy/destroy keep their pre-existing, already-tested
  single-code-per-operation errors (see §6).

## 10. Testing & verification

- **Backend**: 582/582 tests passing (up from a 455-test Phase 24 baseline) — including region discovery
  (moto for AWS, mocked SDK clients for Azure/GCP/OCI/Alibaba), the full 25-path resource inventory suite,
  33 provisioning tests (mocked-SDK success/failure per provider + 6 real HTTP/moto end-to-end
  integration tests covering confirm-mismatch, invalid resource type, ownership 403s, and audit-log
  persistence on both success and failure), and 25E's error-taxonomy/retry/TTL/default-region tests.
  Every provisioning test runs against moto or mocked SDK clients only — none is capable of touching a
  real cloud account.
- **Frontend**: 87/87 Vitest tests passing (up from 64), `tsc -b` clean.
- **Live verification**: both containers rebuilt and restarted from the final 25F state; confirmed every
  new endpoint (`regions`, `refresh-regions`, `region`, `resources`, `resources/deploy`,
  `resources/{type}/{id}`) present in the live OpenAPI schema. A real end-to-end round trip was then
  exercised against the actually-running stack: registered a fresh user, connected a real AWS account
  with a deliberately invalid (but well-formed) credential pair, and confirmed —
  - `GET .../regions` made a genuine network call to real AWS's EC2 endpoint and cleanly surfaced
    `422 AWS_REGION_CREDENTIALS_REJECTED` (proving the new region-discovery taxonomy end-to-end against
    real AWS, not just moto);
  - `GET .../resources?category=compute` cleanly surfaced `422 AWS_RESOURCE_INVENTORY_FAILED` against
    the same real, rejected request;
  - `POST .../resources/deploy` (storage) made a genuine `CreateBucket` call against real AWS, which
    cleanly rejected the fake access key with `422 AWS_DEPLOY_FAILED`, and — confirmed directly against
    the live database — a real `AuditLog` row was written recording the attempt and its exact failure
    reason;
  - `DELETE .../resources/storage/{id}` with a mismatched `confirm` value cleanly returned
    `422 DESTROY_CONFIRMATION_MISMATCH` against the live stack.
  This mirrors this project's established live-verification pattern for AWS-dependent features (Phase
  12): a deliberately invalid real credential pair proves the real network path, real error handling,
  and real audit-log persistence end-to-end, without requiring (or risking) a genuine cloud account with
  real billable resources. The full moto-emulated deploy→destroy→audit-log→new-region-notification round
  trip — which *does* require a successful create/delete — is proven by the automated integration test
  suite instead (a real HTTP request cycle through the real service layer against moto's real AWS
  emulation and a real database, exactly as `test_cloud_provisioning.py` and `test_cloud_region_sync.py`
  already do), since moto only patches `botocore` inside the pytest process, not the separately-running
  live server container.

## 11. Sub-phase commit history

| Sub-phase | Commit | Scope |
|---|---|---|
| 25A | `498a343` | region discovery foundation — AWS/Azure/GCP `list_regions`, migration, sync service, endpoints, frontend |
| 25B | `94c71a7` | Oracle Cloud + Alibaba Cloud built from scratch, registered in the factory |
| 25C | `c8f428b` | read-only resource inventory, 5 categories × 5 providers |
| 25D | `fd1d73e` | provisioning deploy()/destroy(), confirm-to-destroy, audit trail |
| 25E | `703a78b` | error taxonomy, retry consistency, TTL cache gate, default-all region |
| 25F | (this commit) | full regression, live verification, this document |
