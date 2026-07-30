# Phase 28 — Real-Time Metrics/Cost Sync for IBM Cloud and DigitalOcean

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 28 (a direct follow-up to Phase 27's IBM Cloud/DigitalOcean backend integrations - both had real
region discovery, resource inventory, and provisioning, but neither had the real-time metrics/cost sync
every other provider already has. This phase closes that gap as far as each provider's own real APIs
genuinely allow, disclosing the one place they don't)
Status: **Complete**

---

## 1. Overview

- **DigitalOcean** now has real-time Droplet metrics **and** real billing sync - both fully implemented
  against DigitalOcean's own official `pydo` SDK.
- **IBM Cloud** now has real billing sync (`UsageReportsV4`, IBM's own official Usage Reports API).
  Real-time metrics is **deliberately not implemented** - IBM Cloud Monitoring is a separate Sysdig-based
  product requiring a per-instance agent this platform cannot install, and IBM publishes no official
  Python SDK for its query API either (unlike every other integration in this platform). This is
  disclosed via a specific `IBM_MONITORING_NOT_YET_SUPPORTED` error, not silently skipped or faked.

No existing endpoint, schema, or frontend code changed - `POST /deployments/{id}/sync-cloud-metrics` and
`POST /projects/{id}/cloud-costs/sync` already dispatch generically by provider name (see
`CloudSyncService._PROVIDER_FETCHERS` / `CloudCostService._PROVIDER_COST_FETCHERS`); this phase is
purely two new registry entries plus the fetcher modules behind them.

## 2. DigitalOcean real-time metrics - genuinely more complete than any other provider here

`app/integrations/digitalocean_monitoring.py` calls `pydo`'s `monitoring.get_droplet_*_metrics` methods
(DigitalOcean's real, documented Prometheus-compatible `/v2/monitoring/metrics/droplet/*` API). Unlike
every other provider in this platform, DigitalOcean's Droplet metrics genuinely include **memory and
disk** (not just CPU/network) without requiring a separately-installed agent - the monitoring agent
ships pre-installed on every Droplet by default. AWS/Azure/GCP/OCI/Alibaba all disclose memory/disk as
unavailable (`0.0`) without a customer-installed agent; DigitalOcean is the first provider here that
doesn't need that disclosure for those two fields.

CPU is published by DigitalOcean as a Prometheus-style counter broken down by a `mode` label
(idle/user/system/iowait/...), not a ready-made percentage. `cpu_usage_percent` is derived as
`100 - idle%` when an "idle" series is present (the standard Linux CPU-accounting convention), falling
back to the sum of all non-idle series when it isn't.

## 3. Real billing sync for both providers

- **DigitalOcean** (`app/integrations/digitalocean_billing.py`): `invoices.list()` (finalized months
  only - the current month's `invoice_preview` is a separate, deliberately-excluded key, giving the same
  "closed months only" behavior as AWS/Azure/IBM without extra logic) then `invoices.get_by_uuid()` per
  invoice for the real per-product cost breakdown.
- **IBM Cloud** (`app/integrations/ibm_usage_reports.py`): `UsageReportsV4.get_account_usage(account_id,
  billingmonth)` per requested month, grouped by resource. A month with genuinely no usage report yet
  (HTTP 404) is skipped rather than treated as a hard failure. The account ID is resolved fresh each call
  via the same `IamIdentityV1.get_api_keys_details()` call `IbmCloudProviderClient._identity()` already
  uses (Phase 27) - no new required credential field.

## 4. A real finding from live verification

Live verification (a deliberately invalid API key/token against the real IBM Cloud Usage Reports and
real DigitalOcean Invoices APIs) confirmed both new billing paths make genuine network calls and fail
cleanly: IBM's account-ID resolution step correctly surfaced the same real `400`-not-`401` credential
rejection Phase 27 already discovered and classified; DigitalOcean's invoices API cleanly rejected the
fake token with a real `401 Unable to authenticate you`, mapped to `DIGITALOCEAN_BILLING_REQUEST_FAILED`.

## 5. Known, disclosed limitations

- **IBM Cloud Monitoring (metrics) is not implemented** - see §1. This is the one remaining capability
  gap between IBM Cloud and the other 6 providers in this platform.
- **No emulator exists for either provider** (unlike AWS's `moto`) - both new fetcher modules are
  verified only against mocked SDK client responses, the same disclosed caveat as every other IBM/
  DigitalOcean/OCI/Alibaba integration in this project.
- **DigitalOcean's billing breakdown is by product, not by fine-grained resource** - `invoice_items`
  group by `product` (e.g. "Droplets", "Spaces"), coarser than AWS Cost Explorer's per-resource-type
  granularity but the real breakdown DigitalOcean's own invoicing exposes.

## 6. Testing & verification

- 21 new backend tests (`test_digitalocean_monitoring.py`, `test_digitalocean_billing.py`,
  `test_ibm_usage_reports.py`, plus wiring tests in `test_ibm_provider.py`/`test_digitalocean_provider.py`/
  `test_cloud_sync.py`/`test_cloud_cost_sync.py`) covering the CPU idle/non-idle derivation, memory/disk
  byte-delta math, no-datapoints disclosure, the full monthly-cost grouping/skip-zero-cost/closed-months-
  only behavior, and the real HTTP sync endpoints end to end for both providers.
- Full regression: 663/663 backend, 87/87 frontend (no frontend changes this phase).
- Live verification: rebuilt/restarted the backend container; exercised real cost sync against the
  running stack with deliberately invalid credentials for both providers through the actual
  `POST /projects/{id}/cloud-costs/sync` endpoint - each made a genuine network call to the real IBM
  Cloud / DigitalOcean billing API and cleanly reported a classified 422.

## 7. Commit history

| Commit | Scope |
|---|---|
| (this commit) | DigitalOcean metrics + billing fetchers, IBM billing fetcher, registry wiring, tests, docs |
