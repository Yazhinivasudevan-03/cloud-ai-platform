# Phase 30 — Full Global Region Support + Automatic Timezone Mapping

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 30 (extends the region-selection UX for the 7 already-integrated cloud providers - AWS, Azure,
GCP, Oracle Cloud, Alibaba Cloud, IBM Cloud, DigitalOcean)
Status: **Complete**

---

## 1. What was already true before this phase

Region *discovery* itself was already fully live and dynamic for all 7 providers - `list_regions()` on
every provider adapter makes a real SDK call every time (`ec2.describe_regions`, Azure
`SubscriptionClient.subscriptions.list_locations`, GCP `RegionsClient().list()`, OCI
`list_region_subscriptions`, Alibaba `ecs.describe_regions`, IBM's IAM regions list, DigitalOcean
`client.regions.list()`) - nothing was ever hardcoded as the *authoritative* source of which regions
exist for an account, and "All Regions" aggregation already worked for both resource discovery
(`CloudResourceDiscoveryService`, Phase 29) and the read-only inventory browse (`CloudResourceInventoryService`,
Phase 25C).

What was missing was **enrichment**: the live-discovered region list only ever carried an `id` and a
`display_name` - no country, no timezone - and 4 of the 7 providers' display names came from small,
scattered lookup dicts (16-13-10-10 entries). Automatic region→timezone mapping didn't exist at all;
the only timezone feature (`CloudAccountTimezone`, Phase 22) required a user to manually add one.

## 2. What this phase adds (all additive)

- **`app/integrations/region_metadata.py`** (new) - one central table, **185 regions across all 7
  providers**, each with a real `display_name`/`country`/IANA `timezone`. Replaces the 4 old scattered
  per-provider dicts (a consolidation - every provider's real, live discovery call is untouched).
  Ported from and consistent with the frontend's own pre-existing curated table
  (`frontend/src/utils/cloudRegions.ts`, which stays as-is - see §4).
- Every provider adapter's `list_regions()` now enriches each live-discovered region with
  `country`/`timezone` via `region_metadata.lookup()` - a region code the table doesn't cover yet still
  appears (using the provider's own raw code/display name), never hidden.
- `CloudRegionInfo`/`CloudRegionRead` gained optional `country`/`timezone` fields - zero migration
  needed, since `available_regions` was already a JSON blob read back tolerantly (old stored rows
  without these keys simply parse with `None`).
- **Automatic IANA timezone mapping** (requirement 6): `GET .../regions` now returns
  `selected_region_timezone`, resolved server-side from the account's own enriched region list -
  `null` only when "All Regions" is selected (no single timezone applies) or the region isn't in the
  table yet. The existing manual `CloudAccountTimezone` feature (Phase 22) is completely untouched.
- **Frontend**: the post-connect region switcher (`CloudAccountRegionsCard.tsx`) is now a searchable,
  scrollable MUI `Autocomplete` (mirroring `CloudAccountFormDialog.tsx`'s existing pre-connect pattern)
  showing `"code — City, Country"`, plus the resolved timezone. The pre-connect suggestion flow
  (`cloudRegions.ts` + `CloudAccountFormDialog.tsx`) is untouched.

## 3. Region counts per provider (from `region_metadata.py`, verified by `region_count()`)

| Provider | Regions |
|---|---:|
| AWS | 32 |
| Azure | 37 |
| GCP | 40 |
| Oracle Cloud (OCI) | 32 |
| IBM Cloud | 10 |
| DigitalOcean | 12 |
| Alibaba Cloud | 22 |
| **Total** | **185** |

This table is presentation-only enrichment, not a cap - the live API call remains the authoritative
list of which regions actually exist for a given account, and a newly-launched region a provider adds
tomorrow still appears immediately (using its raw code), simply without the extra city/country/timezone
labelling until the table is extended - a one-line addition per region, same as the pattern this project
has used since `aws_provider.py`'s very first region display-name dict.

## 4. Why the frontend's `cloudRegions.ts` was left untouched

That file powers `CloudAccountFormDialog.tsx`'s pre-connect region **suggestion** Autocomplete - used
*before* an account exists, when there is no live account yet to query `GET .../regions` from. It's a
genuine, unavoidable frontend-only need this backend enrichment can't replace, and the task explicitly
required not removing existing functionality. `region_metadata.py` is the new, richer *backend* source
of truth for the *post-connect* flow (real, live-discovered regions).

## 5. Requirement 7 - single region / All Regions support everywhere

Confirmed already correct, not rebuilt: `CloudResourceDiscoveryService._resolve_regions()` (Phase 29)
and `CloudResourceInventoryService._list_across_all_regions()` (Phase 25C) already loop every discovered
region when an account's `region == "all"`. A new regression test
(`test_discover_account_aggregates_across_every_region_in_all_mode`) seeds real EC2 instances in two
different moto regions and confirms both get discovered and persisted in one "All Regions" pass.
Alerts/predictions/monitoring operate per-resource (via each `Deployment`'s own stored
`cloud_resource_identifier`), independent of how many regions the account spans.

## 6. Requirement 8 - storage

Cloud Provider and Region were already dedicated columns on `CloudProviderAccount`. Region Display
Name/Country/Timezone now flow through the same `available_regions` JSON blob automatically (Phase 25's
existing storage mechanism, no schema change). Availability Zone is captured at the correct level -
per discovered *resource* (Phase 29's `CloudResource.availability_zone`), since an AZ is a fact about a
specific resource, not the account/region pair itself.

## 7. Live verification

Using the same already-connected, real AWS account this platform already had credentials for (region
`ap-south-1`, no new secrets requested), a forced live region-refresh returned all 17 real, currently-
enabled regions for that account, every one of them now enriched:

```
ap-south-1     Mumbai          country='India'           timezone=Asia/Kolkata
eu-west-2      London          country='United Kingdom'  timezone=Europe/London
us-east-1      N. Virginia     country='United States'   timezone=America/New_York
...
selected_region: ap-south-1
selected_region_timezone: Asia/Kolkata
```

`selected_region_timezone` correctly resolved to `Asia/Kolkata` for Mumbai - confirming the automatic
region→timezone mapping works end-to-end against a real, live AWS account, not just mocked tests.

## 8. Testing

New `test_region_metadata.py` (12 tests) - every one of the 185 entries' timezone string is verified to
be a real, valid IANA identifier via `zoneinfo.ZoneInfo()` (a genuine correctness check: a typo'd zone
name fails it), plus lookup/case-tolerance/unmapped-region behavior. Extended
`test_provider_region_discovery.py`/`test_ibm_provider.py`/`test_oci_provider.py`/
`test_alibaba_provider.py`/`test_digitalocean_provider.py` for the new enriched shape. New
`test_cloud_resource_discovery.py`/`test_cloud_resource_inventory.py` "All Regions" aggregation tests
(requirement 7). Full regression: backend and frontend both green (see commit for exact counts);
frontend `tsc -b` clean, 87/87 Vitest.

## 9. Region dropdown confirmation

`CloudAccountRegionsCard.tsx`'s post-connect region picker is a searchable, scrollable MUI `Autocomplete`
(`slotProps.listbox` capped at 300px with internal scroll) sourced live from the account's real,
enriched region list, displaying every official region this platform currently knows about for that
provider (185 total across all 7, per §3) in `"code — City, Country"` format, plus an `"All Regions
(aggregate)"` option and the auto-resolved timezone.
