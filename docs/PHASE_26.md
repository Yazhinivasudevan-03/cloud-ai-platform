# Phase 26 — Cloud Credential Configuration Workflow

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 26 (replace the raw backend error a user previously saw when connecting an account with missing/
invalid credentials - e.g. `"AWS credentials must include 'access_key_id' and 'secret_access_key'"` -
with a proper, provider-specific credential configuration workflow: structured fields, a real live
"Test Connection" step, and gated monitoring until credentials are actually proven to work)
Status: **Complete**

---

## 1. Overview

Extends the existing Cloud Account connect/edit dialog and Cloud Account detail page - no existing
functionality removed, no backend architecture rewritten (the request's explicit constraint). Before
this phase, credentials were entered as free-text key/value pairs with no pre-save validation; the
first time anything tried to actually use them (a region sync, a resource-inventory read), whatever
raw `ValidationAppError` message the provider's SDK produced was shown directly to the user.

## 2. Database changes

One additive migration (`7d2e8fc521a2`):

- `cloud_provider_accounts.credentials_validated` - `BOOLEAN NOT NULL`, backfilled `True` for every
  pre-existing account (preserving today's implicit "already connected = already trusted" behavior),
  `False` at the ORM level for any brand-new account - only a real, successful
  `POST /{id}/validate-credentials` call ever flips it.
- `cloud_provider_accounts.credentials_validated_at` - nullable `DATETIME`.

## 3. Backend

- **`CloudProviderClient.test_connection()`/`_identity()`** (new, in `cloud_provider_client.py`) - a
  real, live proof a credential pair works. The default implementation reuses `list_regions()` (already
  a real, classified-error network call per provider since Phase 25E) as the connectivity proof, then
  validates the configured region is one of the ones actually discovered, then calls `_identity()` for
  best-effort `account_id`/`account_alias`/`principal`. AWS overrides `test_connection()` entirely with
  a dedicated STS `GetCallerIdentity` call (the specific mechanism the request named) plus a live
  `DescribeRegions` region-validity check and a best-effort IAM `ListAccountAliases`; Azure/GCP/OCI
  override only `_identity()` (subscription display name, service account email, tenancy name).
- **New AWS error taxonomy for the credential-test path specifically**: `AWS_INVALID_ACCESS_KEY`,
  `AWS_INVALID_SECRET_KEY`, `AWS_ACCESS_DENIED`, `AWS_SESSION_TOKEN_EXPIRED`, `AWS_REGION_INVALID`,
  `AWS_NETWORK_ERROR` - each read from a real, distinct AWS `Error.Code`, never guessed. This is a
  narrower, credential-test-specific sibling to the region-discovery taxonomy Phase 25E already built.
- **`POST /cloud-provider-accounts/test-connection`** (new) - stateless, never persists anything; the
  pre-save "Test Connection" button's endpoint.
- **`POST /cloud-provider-accounts/{id}/validate-credentials`** (new) - re-verifies the already-saved
  account's stored credentials server-side (never trusts a client-supplied "it passed" flag) and, only
  on success, sets `credentials_validated=True` + `credentials_validated_at=now()`, then kicks off an
  immediate best-effort region sync so monitoring begins right away.
- `CloudProviderAccountService.update()` resets `credentials_validated` to `False` whenever credentials
  are replaced, forcing re-validation.
- `CloudSyncService.sync_deployment()` and `CloudRegionSyncService.sync_all_regions()` (the scheduled
  sweeps) now skip/reject any account whose `credentials_validated` is `False` - monitoring never runs
  against known-unconfigured credentials.

## 4. Frontend

- `CloudAccountFormDialog` renders structured, provider-specific credential fields (AWS/Azure/GCP/OCI/
  Alibaba at the time) instead of the generic key/value editor, plus a "Test Connection" button showing
  either a "✅ Connection Successful" panel (account ID/alias/principal/region/status) or the exact
  failure reason - never a raw backend message.
- After a successful save with new credentials, the dialog automatically calls `validate-credentials` in
  the background (best-effort, matching the existing timezone-auto-association pattern already
  established in this same dialog).
- `CloudAccountDetailPage`: an unvalidated account shows "Cloud credentials are required before
  monitoring can begin." with a "Configure {Provider} Credentials" button instead of the Regions/
  Resources/deployments/alerts cards - those cards, and their queries, simply aren't mounted until
  `credentials_validated` is true.
- `DashboardPage`: an unvalidated account's card shows "No cloud credentials configured." and a
  "Configure Credentials" button in place of "Monitor".
- `CloudAccountsPage`: new "Credentials" status column (Validated / Not configured).

## 5. Testing & verification

- 22 new/updated backend tests (`test_cloud_credential_validation.py`), 2 new scheduled-sweep gating
  tests, 3 existing test fixtures updated to explicitly mark their accounts as already-validated (they
  test other subsystems, not this workflow). Full regression at the time: 604/604 backend, 87/87
  frontend.
- Live verification: exercised the real flow against the running stack with a deliberately invalid
  (well-formed) AWS credential pair - Test Connection and validate-credentials both made genuine network
  calls to real AWS and cleanly reported `AWS_INVALID_ACCESS_KEY` (422, not a raw 500).

## 6. Known, disclosed limitation (resolved in Phase 27)

At the time this phase shipped, IBM Cloud and DigitalOcean had no backend `CloudProviderClient` adapter
at all (UI-only "connect" since Phase 24) - their credential forms used the generic key/value editor
with "Test Connection" honestly disclosed as unavailable rather than faked. **Phase 27 built real
backend integrations for both**, and this disclosure no longer applies - see `docs/PHASE_27.md`.

## 7. Commit

`7433967` - "Cloud Credential Configuration workflow: replace raw backend errors with a real Test
Connection / Save / auto-validate flow"
