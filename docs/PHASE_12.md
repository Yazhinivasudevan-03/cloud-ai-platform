# Phase 12 — Real-Time Cloud Provider Metrics Sync

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 12 (post-completion feature addition, beyond the original 10-phase plan)
Status: **Complete and verified**

---

## 1. Overview

Requested directly as "make the platform test in real time" (clarified as:
pull genuine live metrics from the real cloud provider accounts configured
in Phase 11, rather than relying on manually-posted or synthetic
`resource_usage` data). This phase adds a scheduled and on-demand sync
that fetches real telemetry from AWS CloudWatch for any deployment linked
to an AWS `CloudProviderAccount`, and writes it into the existing
`resource_usage` table through the same ingestion path already used by
manual entry and the ML pipeline.

## 2. Objectives Completed

- [x] `Deployment.cloud_provider_account_id` / `cloud_resource_identifier` fields + migration, linking a deployment to one of the user's own Phase 11 cloud accounts and a specific provider resource (e.g. an EC2 instance ID)
- [x] Real AWS CloudWatch integration (`app/integrations/aws_cloudwatch.py`) using genuine `boto3` calls against `GetMetricData` - not a stub, not a simulation
- [x] `CloudSyncService`: on-demand sync (`POST /deployments/{id}/sync-cloud-metrics`) and a scheduled job (`register_cloud_sync_job`, every `CLOUD_SYNC_INTERVAL_MINUTES`) that syncs every cloud-linked deployment, tolerating individual failures without aborting the batch
- [x] Ownership check reused from the established pattern: a deployment can only be linked to a cloud account owned by the same user (`403 NOT_YOUR_CLOUD_ACCOUNT`)
- [x] 10 new backend tests verified against `moto`'s real AWS API emulation (in-process, genuine boto3/botocore request path, no live AWS account needed)
- [x] Frontend "Cloud Sync" tab on the Deployment detail page: link/change a cloud account + resource identifier, trigger a manual sync, see success/error feedback
- [x] Full live verification: real HTTP calls through the running Docker Compose stack (backend + MySQL + rebuilt frontend), a real browser driving the new tab, and a real (deliberately fake) AWS credential pair proving the error path is clean end-to-end

## 3. Architecture Decisions

### Only AWS wired up this pass, dispatched by a provider→function map
`CloudSyncService._PROVIDER_FETCHERS = {"aws": fetch_ec2_resource_usage}`.
Azure and GCP accounts (already fully supported as *storage* since Phase
11 - any provider name, any credentials shape) simply aren't wired to a
metrics fetcher yet; syncing one raises a clear
`CLOUD_SYNC_PROVIDER_NOT_SUPPORTED` error rather than silently doing
nothing or fabricating data. Adding Azure/GCP later means writing one more
`fetch_*` module with the same signature and adding one dict entry - the
service, endpoint, scheduler, and UI never need to change.

### Only CPU and network, honestly - no fabricated memory/disk
EC2's default ("basic") CloudWatch monitoring only reports
`CPUUtilization`, `NetworkIn`, and `NetworkOut`. Memory and disk usage
require the CloudWatch Agent installed on the instance itself, which this
platform has no way to assume is present. Rather than estimating or
fabricating those two `ResourceUsage` fields, they are reported as `0.0`
with the limitation documented in code and here, consistent with this
project's practice of disclosing gaps rather than hiding them.

### `moto` over LocalStack for testing
Both give a real AWS API surface to test against without touching a real
account. `moto[cloudwatch]` was chosen because it runs in-process (via
`@mock_aws`, intercepting the real `boto3`/`botocore` HTTP call), needing
no extra container, while still exercising the exact SDK code path that
would run against genuine AWS - only the transport is faked, not the
application code under test.

### A short forward buffer on the query's `EndTime` (real bug, found and fixed)
The first implementation used `end_time = datetime.now(timezone.utc)`
with no buffer as both the query's `EndTime` and the basis for
`start_time`. Tests failed with `NO_CLOUDWATCH_DATA` even though a
matching datapoint had just been seeded. A standalone diagnostic script
(seeding a datapoint, then calling `get_metric_data` with `EndTime=now`
vs. `EndTime=now+1s`) proved the root cause directly: CloudWatch's
`Period` buckets are `[T, T+period)`, so a query whose `EndTime` lands
exactly on "now" can exclude a datapoint stamped at that same instant,
because the bucket containing it hasn't closed as far as the query window
is concerned. Fixed by computing `end_time` with a 1-minute forward
buffer (`start_time` shifted out by the same amount so the lookback
window size is unaffected) - this isn't a workaround for a moto quirk,
it reflects genuine CloudWatch bucket-boundary semantics that would bite
identically against real AWS.

### Wrapping `botocore` exceptions as clean errors (real bug, found via live browser verification)
`moto` does not validate credentials by default, so the original test
suite never exercised what happens when AWS itself rejects a request.
Manual end-to-end verification through the real running stack - linking a
deployment to a cloud account holding a deliberately fake AWS key pair and
clicking "Sync now" in the browser - surfaced a raw, unhandled 500
(`botocore.exceptions.ClientError: InvalidClientTokenId`) instead of the
intended clean `ErrorAlert` message. Fixed by catching
`botocore.exceptions.ClientError` (bad/expired/insufficient-permission
credentials, throttling, wrong region, etc.) and `botocore.exceptions.BotoCoreError`
(network/connection failures) in `fetch_ec2_resource_usage`, re-raising
both as `ValidationAppError(code="CLOUDWATCH_REQUEST_FAILED")` - a 422
with a specific machine-readable code and AWS's own error message, the
same shape every other expected failure in this codebase already takes.
A dedicated unit test (`test_fetch_ec2_resource_usage_wraps_invalid_credentials_cleanly`)
mocks a `ClientError` directly, since `moto` itself won't produce one.

## 4. API Endpoints

`POST /api/v1/deployments/{deployment_id}/sync-cloud-metrics` - operator/admin only; pulls live metrics right now for one deployment, returns a `CloudSyncResult`
`PUT /api/v1/deployments/{deployment_id}` - now also accepts `cloud_provider_account_id` / `cloud_resource_identifier` to link/change/clear the cloud link (ownership of the cloud account is checked)

The scheduled job calls `CloudSyncService.sync_all()` internally (not exposed as an endpoint) every `CLOUD_SYNC_INTERVAL_MINUTES` (default 15), syncing every deployment that has both a `cloud_provider_account_id` and a `cloud_resource_identifier` set.

## 5. Verification Results

- Backend test suite: **149/149 passing** (139 existing + 10 new: 5 CloudWatch integration tests, 5 CloudSync service/endpoint tests)
- Root-cause bug (query `EndTime` boundary) diagnosed via a standalone script directly exercising `moto`, confirmed fixed by re-running the previously-failing tests
- Second bug (unhandled `ClientError` → 500) found only by live browser verification (not caught by the mocked-credential test suite, since `moto` doesn't validate credentials) - fixed and covered by a new mocked-`ClientError` unit test, then re-verified live
- Live verification, in order: registered a test user via the real API, granted it the `operator` role directly in MySQL (registration always assigns `viewer`, by design - there is no self-promotion path), created a real `CloudProviderAccount` with a deliberately fake AWS key pair, created a project/microservice/deployment, linked the deployment to the account with a fake resource identifier, and called the sync endpoint twice: once through a real browser driving the new "Cloud Sync" tab (found the 500), and once via direct HTTP after the fix, confirming the response is now `422 {"error":{"code":"CLOUDWATCH_REQUEST_FAILED","message":"AWS CloudWatch rejected the request (InvalidClientTokenId): ..."}}`
- Frontend: `tsc --noEmit` and `eslint` both clean on the modified file; the "Cloud Sync" tab was screenshotted mid-flow (not linked → dialog open → dropdown populated → linked → sync error) confirming MUI styling, the account dropdown, and the `ErrorAlert`/`Alert` components all render correctly
- Test data created during live verification (test user, cloud account, project/microservice/deployment) was deleted afterward, not left in the shared dev database

## 6. Known Limitations (disclosed, not hidden)

- **Only AWS EC2 is wired to a real fetcher.** Azure and GCP accounts can be stored (Phase 11) but cannot be synced yet - attempting to returns a clear `CLOUD_SYNC_PROVIDER_NOT_SUPPORTED` error, not a silent no-op.
- **Memory and disk usage are always `0.0` for AWS-synced data.** EC2's basic monitoring doesn't expose them without the CloudWatch Agent, which this platform cannot assume is installed on the target instance.
- **No genuine AWS account was used for verification** - only `moto` (automated tests) and a deliberately invalid real AWS credential pair (live manual verification, which legitimately proves the request reaches real AWS and real AWS's rejection is handled cleanly, but does not prove a *successful* real sync against a real running EC2 instance, since no such instance/account was available in this environment).
