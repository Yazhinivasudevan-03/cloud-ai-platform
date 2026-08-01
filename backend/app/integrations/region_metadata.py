"""Central cloud-region metadata table (Phase 30) - the one place display
name / country / IANA timezone is ever defined for any provider's regions
in this project, replacing the 4 small, scattered per-provider display-name
dicts that used to live inside aws_provider.py/gcp_provider.py/
oci_provider.py/ibm_provider.py.

This table is presentation-only enrichment, never the authoritative source
of *which* regions exist for an account - every provider adapter's
list_regions() still makes a real, live SDK call every time (AWS
DescribeRegions, Azure SubscriptionClient.subscriptions.list_locations,
GCP RegionsClient.list, OCI list_region_subscriptions, Alibaba
DescribeRegions, IBM's IAM regions list, DigitalOcean regions.list) - this
module only decorates whatever the live call returns. A region code the
live API returns that isn't in this table yet (a newly-launched region, or
one this table simply doesn't cover yet) is never hidden - lookup() returns
None and callers fall back to the provider's own raw code/display name,
exactly matching the disclosed convention this project has used since
aws_provider.py's original _AWS_REGION_DISPLAY_NAMES.

Ported from frontend/src/utils/cloudRegions.ts (the pre-connect region
Autocomplete's existing curated table) so the two never drift out of sync
by accident - that file stays the frontend's own source for its pre-connect
suggestion flow (which has no live account to query yet); this module is
the backend's equivalent for enriching live-discovered regions post-connect.

Adding/correcting a region (e.g. a provider launches a new one) is a
one-line addition to the relevant dict below - nothing else in the project
needs to change.
"""
from typing import TypedDict


class RegionMetadata(TypedDict):
    display_name: str
    country: str
    timezone: str


def _r(display_name: str, country: str, timezone: str) -> RegionMetadata:
    return {"display_name": display_name, "country": country, "timezone": timezone}


_AWS_REGIONS: dict[str, RegionMetadata] = {
    "us-east-1": _r("N. Virginia", "United States", "America/New_York"),
    "us-east-2": _r("Ohio", "United States", "America/New_York"),
    "us-west-1": _r("N. California", "United States", "America/Los_Angeles"),
    "us-west-2": _r("Oregon", "United States", "America/Los_Angeles"),
    "ap-south-1": _r("Mumbai", "India", "Asia/Kolkata"),
    "ap-south-2": _r("Hyderabad", "India", "Asia/Kolkata"),
    "ap-east-1": _r("Hong Kong", "Hong Kong", "Asia/Hong_Kong"),
    "ap-southeast-1": _r("Singapore", "Singapore", "Asia/Singapore"),
    "ap-southeast-2": _r("Sydney", "Australia", "Australia/Sydney"),
    "ap-southeast-3": _r("Jakarta", "Indonesia", "Asia/Jakarta"),
    "ap-southeast-4": _r("Melbourne", "Australia", "Australia/Melbourne"),
    "ap-southeast-5": _r("Kuala Lumpur", "Malaysia", "Asia/Kuala_Lumpur"),
    "ap-southeast-7": _r("Bangkok", "Thailand", "Asia/Bangkok"),
    "ap-northeast-1": _r("Tokyo", "Japan", "Asia/Tokyo"),
    "ap-northeast-2": _r("Seoul", "South Korea", "Asia/Seoul"),
    "ap-northeast-3": _r("Osaka", "Japan", "Asia/Tokyo"),
    "eu-west-1": _r("Dublin", "Ireland", "Europe/Dublin"),
    "eu-west-2": _r("London", "United Kingdom", "Europe/London"),
    "eu-west-3": _r("Paris", "France", "Europe/Paris"),
    "eu-central-1": _r("Frankfurt", "Germany", "Europe/Berlin"),
    "eu-central-2": _r("Zurich", "Switzerland", "Europe/Zurich"),
    "eu-north-1": _r("Stockholm", "Sweden", "Europe/Stockholm"),
    "eu-south-1": _r("Milan", "Italy", "Europe/Rome"),
    "eu-south-2": _r("Spain", "Spain", "Europe/Madrid"),
    "ca-central-1": _r("Central Canada", "Canada", "America/Toronto"),
    "ca-west-1": _r("Calgary", "Canada", "America/Edmonton"),
    "sa-east-1": _r("São Paulo", "Brazil", "America/Sao_Paulo"),
    "me-south-1": _r("Bahrain", "Bahrain", "Asia/Bahrain"),
    "me-central-1": _r("UAE", "United Arab Emirates", "Asia/Dubai"),
    "af-south-1": _r("Cape Town", "South Africa", "Africa/Johannesburg"),
    "il-central-1": _r("Tel Aviv", "Israel", "Asia/Jerusalem"),
    "mx-central-1": _r("Central Mexico", "Mexico", "America/Mexico_City"),
}

_AZURE_REGIONS: dict[str, RegionMetadata] = {
    "eastus": _r("East US (Virginia)", "United States", "America/New_York"),
    "eastus2": _r("East US 2 (Virginia)", "United States", "America/New_York"),
    "centralus": _r("Central US (Iowa)", "United States", "America/Chicago"),
    "southcentralus": _r("South Central US (Texas)", "United States", "America/Chicago"),
    "northcentralus": _r("North Central US (Illinois)", "United States", "America/Chicago"),
    "westus": _r("West US (California)", "United States", "America/Los_Angeles"),
    "westus2": _r("West US 2 (Washington)", "United States", "America/Los_Angeles"),
    "westus3": _r("West US 3 (Arizona)", "United States", "America/Phoenix"),
    "canadacentral": _r("Canada Central (Toronto)", "Canada", "America/Toronto"),
    "canadaeast": _r("Canada East (Quebec)", "Canada", "America/Toronto"),
    "brazilsouth": _r("Brazil South (São Paulo)", "Brazil", "America/Sao_Paulo"),
    "northeurope": _r("North Europe (Ireland)", "Ireland", "Europe/Dublin"),
    "westeurope": _r("West Europe (Netherlands)", "Netherlands", "Europe/Amsterdam"),
    "uksouth": _r("UK South (London)", "United Kingdom", "Europe/London"),
    "ukwest": _r("UK West (Cardiff)", "United Kingdom", "Europe/London"),
    "francecentral": _r("France Central (Paris)", "France", "Europe/Paris"),
    "germanywestcentral": _r("Germany West Central (Frankfurt)", "Germany", "Europe/Berlin"),
    "switzerlandnorth": _r("Switzerland North (Zurich)", "Switzerland", "Europe/Zurich"),
    "norwayeast": _r("Norway East (Oslo)", "Norway", "Europe/Oslo"),
    "swedencentral": _r("Sweden Central (Gävle)", "Sweden", "Europe/Stockholm"),
    "polandcentral": _r("Poland Central (Warsaw)", "Poland", "Europe/Warsaw"),
    "italynorth": _r("Italy North (Milan)", "Italy", "Europe/Rome"),
    "spaincentral": _r("Spain Central (Madrid)", "Spain", "Europe/Madrid"),
    "eastasia": _r("East Asia (Hong Kong)", "Hong Kong", "Asia/Hong_Kong"),
    "southeastasia": _r("Southeast Asia (Singapore)", "Singapore", "Asia/Singapore"),
    "japaneast": _r("Japan East (Tokyo)", "Japan", "Asia/Tokyo"),
    "japanwest": _r("Japan West (Osaka)", "Japan", "Asia/Tokyo"),
    "koreacentral": _r("Korea Central (Seoul)", "South Korea", "Asia/Seoul"),
    "centralindia": _r("Central India (Pune)", "India", "Asia/Kolkata"),
    "southindia": _r("South India (Chennai)", "India", "Asia/Kolkata"),
    "westindia": _r("West India (Mumbai)", "India", "Asia/Kolkata"),
    "australiaeast": _r("Australia East (Sydney)", "Australia", "Australia/Sydney"),
    "australiasoutheast": _r("Australia Southeast (Melbourne)", "Australia", "Australia/Melbourne"),
    "southafricanorth": _r("South Africa North (Johannesburg)", "South Africa", "Africa/Johannesburg"),
    "uaenorth": _r("UAE North (Dubai)", "United Arab Emirates", "Asia/Dubai"),
    "qatarcentral": _r("Qatar Central (Doha)", "Qatar", "Asia/Qatar"),
    "israelcentral": _r("Israel Central", "Israel", "Asia/Jerusalem"),
}

_GCP_REGIONS: dict[str, RegionMetadata] = {
    "us-central1": _r("Iowa", "United States", "America/Chicago"),
    "us-east1": _r("South Carolina", "United States", "America/New_York"),
    "us-east4": _r("Northern Virginia", "United States", "America/New_York"),
    "us-east5": _r("Columbus", "United States", "America/New_York"),
    "us-west1": _r("Oregon", "United States", "America/Los_Angeles"),
    "us-west2": _r("Los Angeles", "United States", "America/Los_Angeles"),
    "us-west3": _r("Salt Lake City", "United States", "America/Denver"),
    "us-west4": _r("Las Vegas", "United States", "America/Los_Angeles"),
    "us-south1": _r("Dallas", "United States", "America/Chicago"),
    "northamerica-northeast1": _r("Montreal", "Canada", "America/Toronto"),
    "northamerica-northeast2": _r("Toronto", "Canada", "America/Toronto"),
    "southamerica-east1": _r("São Paulo", "Brazil", "America/Sao_Paulo"),
    "southamerica-west1": _r("Santiago", "Chile", "America/Santiago"),
    "europe-west1": _r("Belgium", "Belgium", "Europe/Brussels"),
    "europe-west2": _r("London", "United Kingdom", "Europe/London"),
    "europe-west3": _r("Frankfurt", "Germany", "Europe/Berlin"),
    "europe-west4": _r("Netherlands", "Netherlands", "Europe/Amsterdam"),
    "europe-west6": _r("Zurich", "Switzerland", "Europe/Zurich"),
    "europe-west8": _r("Milan", "Italy", "Europe/Rome"),
    "europe-west9": _r("Paris", "France", "Europe/Paris"),
    "europe-west10": _r("Berlin", "Germany", "Europe/Berlin"),
    "europe-west12": _r("Turin", "Italy", "Europe/Rome"),
    "europe-north1": _r("Finland", "Finland", "Europe/Helsinki"),
    "europe-southwest1": _r("Madrid", "Spain", "Europe/Madrid"),
    "europe-central2": _r("Warsaw", "Poland", "Europe/Warsaw"),
    "asia-south1": _r("Mumbai", "India", "Asia/Kolkata"),
    "asia-south2": _r("Delhi", "India", "Asia/Kolkata"),
    "asia-southeast1": _r("Singapore", "Singapore", "Asia/Singapore"),
    "asia-southeast2": _r("Jakarta", "Indonesia", "Asia/Jakarta"),
    "asia-east1": _r("Taiwan", "Taiwan", "Asia/Taipei"),
    "asia-east2": _r("Hong Kong", "Hong Kong", "Asia/Hong_Kong"),
    "asia-northeast1": _r("Tokyo", "Japan", "Asia/Tokyo"),
    "asia-northeast2": _r("Osaka", "Japan", "Asia/Tokyo"),
    "asia-northeast3": _r("Seoul", "South Korea", "Asia/Seoul"),
    "australia-southeast1": _r("Sydney", "Australia", "Australia/Sydney"),
    "australia-southeast2": _r("Melbourne", "Australia", "Australia/Melbourne"),
    "me-central1": _r("Doha", "Qatar", "Asia/Qatar"),
    "me-central2": _r("Dammam", "Saudi Arabia", "Asia/Riyadh"),
    "me-west1": _r("Tel Aviv", "Israel", "Asia/Jerusalem"),
    "africa-south1": _r("Johannesburg", "South Africa", "Africa/Johannesburg"),
}

# Oracle Cloud Infrastructure - keyed "oci" to match provider_factory.py's
# registry key and OciCloudProviderClient.provider_name.
_OCI_REGIONS: dict[str, RegionMetadata] = {
    "us-ashburn-1": _r("Ashburn", "United States", "America/New_York"),
    "us-phoenix-1": _r("Phoenix", "United States", "America/Phoenix"),
    "us-sanjose-1": _r("San Jose", "United States", "America/Los_Angeles"),
    "ca-toronto-1": _r("Toronto", "Canada", "America/Toronto"),
    "ca-montreal-1": _r("Montreal", "Canada", "America/Toronto"),
    "sa-saopaulo-1": _r("São Paulo", "Brazil", "America/Sao_Paulo"),
    "sa-vinhedo-1": _r("Vinhedo", "Brazil", "America/Sao_Paulo"),
    "sa-santiago-1": _r("Santiago", "Chile", "America/Santiago"),
    "uk-london-1": _r("London", "United Kingdom", "Europe/London"),
    "uk-cardiff-1": _r("Cardiff", "United Kingdom", "Europe/London"),
    "eu-frankfurt-1": _r("Frankfurt", "Germany", "Europe/Berlin"),
    "eu-amsterdam-1": _r("Amsterdam", "Netherlands", "Europe/Amsterdam"),
    "eu-zurich-1": _r("Zurich", "Switzerland", "Europe/Zurich"),
    "eu-madrid-1": _r("Madrid", "Spain", "Europe/Madrid"),
    "eu-marseille-1": _r("Marseille", "France", "Europe/Paris"),
    "eu-milan-1": _r("Milan", "Italy", "Europe/Rome"),
    "eu-paris-1": _r("Paris", "France", "Europe/Paris"),
    "eu-stockholm-1": _r("Stockholm", "Sweden", "Europe/Stockholm"),
    "me-jeddah-1": _r("Jeddah", "Saudi Arabia", "Asia/Riyadh"),
    "me-dubai-1": _r("Dubai", "United Arab Emirates", "Asia/Dubai"),
    "me-abudhabi-1": _r("Abu Dhabi", "United Arab Emirates", "Asia/Dubai"),
    "ap-mumbai-1": _r("Mumbai", "India", "Asia/Kolkata"),
    "ap-hyderabad-1": _r("Hyderabad", "India", "Asia/Kolkata"),
    "ap-tokyo-1": _r("Tokyo", "Japan", "Asia/Tokyo"),
    "ap-osaka-1": _r("Osaka", "Japan", "Asia/Tokyo"),
    "ap-seoul-1": _r("Seoul", "South Korea", "Asia/Seoul"),
    "ap-chuncheon-1": _r("Chuncheon", "South Korea", "Asia/Seoul"),
    "ap-singapore-1": _r("Singapore", "Singapore", "Asia/Singapore"),
    "ap-sydney-1": _r("Sydney", "Australia", "Australia/Sydney"),
    "ap-melbourne-1": _r("Melbourne", "Australia", "Australia/Melbourne"),
    "il-jerusalem-1": _r("Jerusalem", "Israel", "Asia/Jerusalem"),
    "af-johannesburg-1": _r("Johannesburg", "South Africa", "Africa/Johannesburg"),
}

_IBM_REGIONS: dict[str, RegionMetadata] = {
    "us-south": _r("Dallas", "United States", "America/Chicago"),
    "us-east": _r("Washington DC", "United States", "America/New_York"),
    "ca-tor": _r("Toronto", "Canada", "America/Toronto"),
    "br-sao": _r("São Paulo", "Brazil", "America/Sao_Paulo"),
    "eu-gb": _r("London", "United Kingdom", "Europe/London"),
    "eu-de": _r("Frankfurt", "Germany", "Europe/Berlin"),
    "eu-es": _r("Madrid", "Spain", "Europe/Madrid"),
    "au-syd": _r("Sydney", "Australia", "Australia/Sydney"),
    "jp-tok": _r("Tokyo", "Japan", "Asia/Tokyo"),
    "jp-osa": _r("Osaka", "Japan", "Asia/Tokyo"),
}

_DIGITALOCEAN_REGIONS: dict[str, RegionMetadata] = {
    "nyc1": _r("New York 1", "United States", "America/New_York"),
    "nyc2": _r("New York 2", "United States", "America/New_York"),
    "nyc3": _r("New York 3", "United States", "America/New_York"),
    "sfo2": _r("San Francisco 2", "United States", "America/Los_Angeles"),
    "sfo3": _r("San Francisco 3", "United States", "America/Los_Angeles"),
    "tor1": _r("Toronto 1", "Canada", "America/Toronto"),
    "ams3": _r("Amsterdam 3", "Netherlands", "Europe/Amsterdam"),
    "lon1": _r("London 1", "United Kingdom", "Europe/London"),
    "fra1": _r("Frankfurt 1", "Germany", "Europe/Berlin"),
    "sgp1": _r("Singapore 1", "Singapore", "Asia/Singapore"),
    "blr1": _r("Bangalore 1", "India", "Asia/Kolkata"),
    "syd1": _r("Sydney 1", "Australia", "Australia/Sydney"),
}

_ALIBABA_REGIONS: dict[str, RegionMetadata] = {
    "cn-hangzhou": _r("Hangzhou", "China", "Asia/Shanghai"),
    "cn-shanghai": _r("Shanghai", "China", "Asia/Shanghai"),
    "cn-beijing": _r("Beijing", "China", "Asia/Shanghai"),
    "cn-shenzhen": _r("Shenzhen", "China", "Asia/Shanghai"),
    "cn-guangzhou": _r("Guangzhou", "China", "Asia/Shanghai"),
    "cn-qingdao": _r("Qingdao", "China", "Asia/Shanghai"),
    "cn-zhangjiakou": _r("Zhangjiakou", "China", "Asia/Shanghai"),
    "cn-huhehaote": _r("Hohhot", "China", "Asia/Shanghai"),
    "cn-chengdu": _r("Chengdu", "China", "Asia/Shanghai"),
    "cn-hongkong": _r("Hong Kong", "Hong Kong", "Asia/Hong_Kong"),
    "ap-southeast-1": _r("Singapore", "Singapore", "Asia/Singapore"),
    "ap-southeast-2": _r("Sydney", "Australia", "Australia/Sydney"),
    "ap-southeast-3": _r("Kuala Lumpur", "Malaysia", "Asia/Kuala_Lumpur"),
    "ap-southeast-5": _r("Jakarta", "Indonesia", "Asia/Jakarta"),
    "ap-northeast-1": _r("Tokyo", "Japan", "Asia/Tokyo"),
    "ap-northeast-2": _r("Seoul", "South Korea", "Asia/Seoul"),
    "ap-south-1": _r("Mumbai", "India", "Asia/Kolkata"),
    "us-west-1": _r("Silicon Valley", "United States", "America/Los_Angeles"),
    "us-east-1": _r("Virginia", "United States", "America/New_York"),
    "eu-central-1": _r("Frankfurt", "Germany", "Europe/Berlin"),
    "eu-west-1": _r("London", "United Kingdom", "Europe/London"),
    "me-east-1": _r("Dubai", "United Arab Emirates", "Asia/Dubai"),
}

_REGIONS_BY_PROVIDER: dict[str, dict[str, RegionMetadata]] = {
    "aws": _AWS_REGIONS,
    "azure": _AZURE_REGIONS,
    "gcp": _GCP_REGIONS,
    "oci": _OCI_REGIONS,
    "ibm": _IBM_REGIONS,
    "digitalocean": _DIGITALOCEAN_REGIONS,
    "alibaba": _ALIBABA_REGIONS,
}


def lookup(provider: str, region_id: str) -> RegionMetadata | None:
    """Best-effort metadata for one region code - None (never a fabricated
    guess, never an exception) when the provider or region code isn't in
    this table yet. Callers must treat None as "no enrichment available",
    falling back to whatever the live provider API itself returned."""
    return _REGIONS_BY_PROVIDER.get(provider.strip().lower(), {}).get(region_id)


def region_count(provider: str) -> int:
    """Number of regions this table currently covers for one provider -
    used only for reporting/tests, never for validation (the live API call
    is always the authoritative list of which regions actually exist)."""
    return len(_REGIONS_BY_PROVIDER.get(provider.strip().lower(), {}))
