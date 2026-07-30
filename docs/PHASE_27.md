# Phase 27 — IBM Cloud and DigitalOcean: Real Backend Integrations

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 27 (a direct follow-up to Phase 26's Cloud Credential Configuration workflow: IBM Cloud and
DigitalOcean previously had UI-only "connect" buttons since Phase 24 with no real backend adapter at
all - "Test Connection" for either honestly reported that live validation wasn't available. This phase
builds genuine `CloudProviderClient` adapters for both, matching every capability the other 5 providers
already have)
Status: **Complete**

---

## 1. Overview

IBM Cloud and DigitalOcean now have the exact same capability surface as AWS/Azure/GCP/Oracle Cloud/
Alibaba Cloud: real credential validation, live region discovery, a 5-category resource inventory,
compute/storage/networking provisioning, and registration in the one shared `provider_factory.py`
registry - no controller/service/router code branches on provider name for either.

Both adapters are built against each provider's own official SDK:

- **IBM Cloud** - `ibm-vpc` (VPC compute/networking), `ibm-platform-services` (IAM identity, Resource
  Controller), `ibm-cos-sdk` (Cloud Object Storage, S3-compatible), all authenticated with a single IAM
  API key via `ibm-cloud-sdk-core`'s `IAMAuthenticator`.
- **DigitalOcean** - `pydo`, DigitalOcean's own official Python client (generated from their public API
  v2 spec), authenticated with a single personal access token. Storage (Spaces) reuses the existing
  `boto3` dependency pointed at DigitalOcean's S3-compatible endpoint, since Spaces requires its own
  separate access-key/secret-key pair distinct from the API token - a genuine platform distinction,
  disclosed rather than papered over.

Both adapters follow this project's now-established pattern exactly: `tenacity` retry on transient
errors only, the Phase 25E-style region-discovery error taxonomy (credentials rejected/access denied/
throttled/provider outage/no-regions-returned), and honest prerequisite disclosure for anything the
platform cannot fabricate on the caller's behalf.

## 2. Credential shapes

- **IBM Cloud**: `{"api_key": "<IAM API key>", "resource_group_id": "<optional, required only for
  provisioning>", "cos_instance_crn": "<optional, required only for storage>"}`.
- **DigitalOcean**: `{"api_token": "<personal access token>", "spaces_access_key_id": "<optional,
  required only for storage>", "spaces_secret_access_key": "<optional, required only for storage>"}`.

Both keep the "one primary credential" simplicity every other provider in this platform already has -
the two optional fields are only ever required by the specific operations that genuinely need them
(deploying a resource into a specific resource group; listing/creating storage buckets), never by
credential validation or read-only region/resource discovery.

## 3. Resource inventory: a real, disclosed derivation for clusters/databases

Neither IBM Cloud nor DigitalOcean expose a single "list all Kubernetes clusters" / "list all managed
databases" API the way AWS/Azure/GCP do for their one respective service each - IBM in particular has no
comparable SDK client for its Kubernetes Service or any of its ~10 "Databases for X" products at all.

- **IBM Cloud** derives both categories from `ResourceControllerV2.list_resource_instances()` (which
  *does* return every resource instance in the account, of any kind) by filtering each instance's own
  CRN service-name segment against IBM's real, stable naming convention:
  `containers-kubernetes`/`containers-kubernetes-openshift` for clusters, every `databases-for-*`
  service for databases. This is a genuine, disclosed derivation from a real API - not a fabricated
  filter.
- **DigitalOcean** has dedicated, real SDK methods for both (`client.kubernetes.list_clusters()`,
  `client.databases.list_clusters()`), so no derivation is needed there.

## 4. Provisioning

Compute deploy is hard-capped to one fixed, smallest general-purpose size per provider (matching every
other provider's identical cost/blast-radius-bounding rule from Phase 25D):

- IBM Cloud: `bx2-2x8` VPC profile.
- DigitalOcean: `s-1vcpu-1gb` Droplet size.

Honest prerequisite disclosure (the same "disclose, don't fake" stance as every other provider's
`*_DEPLOY_SPEC_INCOMPLETE` error):

- IBM Cloud compute requires `spec.image_id`, `spec.zone`, `spec.subnet_id`, `spec.vpc_id` - a real VPC
  instance needs a VM image, a zone, and a subnet within an existing VPC, none of which this platform
  can fabricate.
- DigitalOcean compute requires `spec.image` (a real Droplet image slug or numeric ID).
- Storage deploy on both requires `spec.name` and destroy relies on the provider's own empty-bucket
  precondition (never force-emptied first) - the same genuine safety feature already established for
  S3/OSS/Azure Storage/GCS.

## 5. A real finding from live verification: IBM's IAM error status code

Live verification against the actual, real IBM Cloud IAM API (a deliberately invalid API key, the same
established pattern from Phase 12/25F/26) revealed that IBM's token endpoint rejects an unknown/invalid
API key with a plain `400 Bad Request`, **not** `401 Unauthorized` as would be the more conventional
choice. The initial error-taxonomy classifier assumed 401; this was caught immediately by live
verification (not assumed away) and fixed - `400` is now treated as `IBM_REGION_CREDENTIALS_REJECTED`
alongside `401`, with a dedicated regression test locking in the real, empirically-confirmed behavior
rather than a guess.

## 6. Known, disclosed limitations

- **No emulator exists for either provider** (unlike AWS's `moto`), and no live account was available to
  validate the full read/write surface against in this environment - both adapters are verified only
  against mocked SDK client responses, the same disclosed caveat this project already applies to Azure/
  GCP/OCI/Alibaba.
- **Neither provider has real-time metrics/cost sync wired up** (the Phase 12/18 `CloudSyncService`/
  `CloudCostService` telemetry pull) - only region discovery, resource inventory, provisioning, and
  credential validation. A deployment linked to either account can still be monitored via manually-
  ingested or Prometheus/Kubernetes-sourced `resource_usage` data, same as before this phase.
- **IBM Cloud Object Storage and DigitalOcean Spaces both require a second, optional credential field**
  specific to storage (`cos_instance_crn` / `spaces_access_key_id`+`spaces_secret_access_key`) - a real
  platform requirement for each, not an inconsistency introduced by this platform.

## 7. Testing & verification

- 37 new backend tests (`test_ibm_provider.py`, `test_digitalocean_provider.py`) covering region
  discovery (success + the full error taxonomy + no-regions-returned), `test_connection()`/`_identity()`,
  all 5 resource-inventory categories, and deploy/destroy for compute/storage/networking (including
  spec-incomplete and missing-storage-credential failures). One existing test
  (`test_provider_factory_supports_every_registered_provider`) updated to include the two new registry
  entries.
- Full regression: 641/641 backend, 87/87 frontend (`tsc -b` clean).
- Live verification: rebuilt/restarted both containers; confirmed the new structured credential fields
  (IAM API Key, Cloud Object Storage instance CRN, Personal Access Token, Spaces Access Key ID) in the
  actually-served frontend bundle; exercised `POST /cloud-provider-accounts/test-connection` against
  the running stack with deliberately invalid credentials for both providers - each made a genuine
  network call to the real IBM Cloud / DigitalOcean API and cleanly reported a classified 422 (not a
  raw 500), which is how the real IBM status-code discrepancy in §5 was actually found.

## 8. Commit history

| Commit | Scope |
|---|---|
| (this commit) | IBM Cloud + DigitalOcean adapters, provider_factory registration, frontend credential fields, tests, docs |
