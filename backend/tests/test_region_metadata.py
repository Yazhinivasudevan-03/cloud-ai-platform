"""Unit tests for Phase 30's central region metadata table
(app/integrations/region_metadata.py) - the module every provider adapter's
list_regions() now enriches its live-discovered regions through."""
from zoneinfo import ZoneInfo

import pytest

from app.integrations import region_metadata

_ALL_PROVIDERS = ("aws", "azure", "gcp", "oci", "ibm", "digitalocean", "alibaba")


def test_lookup_resolves_a_known_region_for_every_provider():
    assert region_metadata.lookup("aws", "us-east-1")["timezone"] == "America/New_York"
    assert region_metadata.lookup("azure", "eastus")["country"] == "United States"
    assert region_metadata.lookup("gcp", "asia-south1")["timezone"] == "Asia/Kolkata"
    assert region_metadata.lookup("oci", "uk-london-1")["timezone"] == "Europe/London"
    assert region_metadata.lookup("ibm", "jp-tok")["timezone"] == "Asia/Tokyo"
    assert region_metadata.lookup("digitalocean", "sgp1")["timezone"] == "Asia/Singapore"
    assert region_metadata.lookup("alibaba", "cn-shanghai")["country"] == "China"


def test_lookup_returns_none_for_an_unmapped_region_or_provider():
    assert region_metadata.lookup("aws", "mars-base-1") is None
    assert region_metadata.lookup("not-a-real-provider", "us-east-1") is None


def test_lookup_is_case_and_whitespace_tolerant_on_provider_name():
    assert region_metadata.lookup(" AWS ", "us-east-1") is not None
    assert region_metadata.lookup("Aws", "us-east-1") is not None


@pytest.mark.parametrize("provider", _ALL_PROVIDERS)
def test_every_entry_has_a_real_iana_timezone(provider):
    # ZoneInfo() raises ZoneInfoNotFoundError for anything that isn't a
    # real IANA identifier - this is a genuine correctness check, not a
    # tautology, since a typo'd zone name would fail it.
    table = region_metadata._REGIONS_BY_PROVIDER[provider]  # noqa: SLF001 - test-only introspection
    assert len(table) > 0
    for region_id, metadata in table.items():
        ZoneInfo(metadata["timezone"])
        assert metadata["display_name"]
        assert metadata["country"]


def test_region_count_matches_table_size():
    for provider in _ALL_PROVIDERS:
        assert region_metadata.region_count(provider) == len(region_metadata._REGIONS_BY_PROVIDER[provider])  # noqa: SLF001


def test_region_count_is_zero_for_an_unknown_provider():
    assert region_metadata.region_count("not-a-real-provider") == 0
