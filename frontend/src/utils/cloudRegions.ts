/** Curated cloud-provider region -> recommended IANA timezone tables - the
 * single central place a region list is ever defined in this project (per
 * the "one config file, not hardcoded throughout" requirement). Powers the
 * Region autocomplete's suggestions in both CloudAccountTimezoneFormDialog
 * and CloudAccountFormDialog, and extends the existing free-text Region
 * field rather than replacing it - a provider with no curated table below
 * (anything typed into the "Other" provider's free-text name) keeps
 * today's plain text entry exactly as before. The user can always override
 * a suggested timezone via the existing searchable IANA dropdown
 * (CloudAccountTimezoneFormDialog) or simply type a region this table
 * doesn't yet know about.
 *
 * Adding/correcting a region (e.g. when a provider launches a new one) is
 * a one-line addition to the relevant array below - nothing else in the
 * project needs to change. */

export interface CloudRegionSuggestion {
  /** What actually gets stored as CloudProviderAccount.region / CloudAccountTimezone.region. */
  code: string;
  /** Human-readable "City, Country" (or just the region name where no single city applies). */
  label: string;
  /** Recommended IANA timezone identifier for this region. */
  timezone: string;
}

const AWS_REGIONS: CloudRegionSuggestion[] = [
  { code: "us-east-1", label: "N. Virginia, United States", timezone: "America/New_York" },
  { code: "us-east-2", label: "Ohio, United States", timezone: "America/New_York" },
  { code: "us-west-1", label: "N. California, United States", timezone: "America/Los_Angeles" },
  { code: "us-west-2", label: "Oregon, United States", timezone: "America/Los_Angeles" },
  { code: "ap-south-1", label: "Mumbai, India", timezone: "Asia/Kolkata" },
  { code: "ap-south-2", label: "Hyderabad, India", timezone: "Asia/Kolkata" },
  { code: "ap-east-1", label: "Hong Kong", timezone: "Asia/Hong_Kong" },
  { code: "ap-southeast-1", label: "Singapore", timezone: "Asia/Singapore" },
  { code: "ap-southeast-2", label: "Sydney, Australia", timezone: "Australia/Sydney" },
  { code: "ap-southeast-3", label: "Jakarta, Indonesia", timezone: "Asia/Jakarta" },
  { code: "ap-southeast-4", label: "Melbourne, Australia", timezone: "Australia/Melbourne" },
  { code: "ap-northeast-1", label: "Tokyo, Japan", timezone: "Asia/Tokyo" },
  { code: "ap-northeast-2", label: "Seoul, South Korea", timezone: "Asia/Seoul" },
  { code: "ap-northeast-3", label: "Osaka, Japan", timezone: "Asia/Tokyo" },
  { code: "eu-west-1", label: "Dublin, Ireland", timezone: "Europe/Dublin" },
  { code: "eu-west-2", label: "London, United Kingdom", timezone: "Europe/London" },
  { code: "eu-west-3", label: "Paris, France", timezone: "Europe/Paris" },
  { code: "eu-central-1", label: "Frankfurt, Germany", timezone: "Europe/Berlin" },
  { code: "eu-central-2", label: "Zurich, Switzerland", timezone: "Europe/Zurich" },
  { code: "eu-north-1", label: "Stockholm, Sweden", timezone: "Europe/Stockholm" },
  { code: "eu-south-1", label: "Milan, Italy", timezone: "Europe/Rome" },
  { code: "eu-south-2", label: "Spain", timezone: "Europe/Madrid" },
  { code: "ca-central-1", label: "Central Canada", timezone: "America/Toronto" },
  { code: "ca-west-1", label: "Calgary, Canada", timezone: "America/Edmonton" },
  { code: "sa-east-1", label: "São Paulo, Brazil", timezone: "America/Sao_Paulo" },
  { code: "me-south-1", label: "Bahrain", timezone: "Asia/Bahrain" },
  { code: "me-central-1", label: "UAE", timezone: "Asia/Dubai" },
  { code: "af-south-1", label: "Cape Town, South Africa", timezone: "Africa/Johannesburg" },
  { code: "il-central-1", label: "Tel Aviv, Israel", timezone: "Asia/Jerusalem" },
];

const AZURE_REGIONS: CloudRegionSuggestion[] = [
  { code: "eastus", label: "East US (Virginia)", timezone: "America/New_York" },
  { code: "eastus2", label: "East US 2 (Virginia)", timezone: "America/New_York" },
  { code: "centralus", label: "Central US (Iowa)", timezone: "America/Chicago" },
  { code: "southcentralus", label: "South Central US (Texas)", timezone: "America/Chicago" },
  { code: "northcentralus", label: "North Central US (Illinois)", timezone: "America/Chicago" },
  { code: "westus", label: "West US (California)", timezone: "America/Los_Angeles" },
  { code: "westus2", label: "West US 2 (Washington)", timezone: "America/Los_Angeles" },
  { code: "westus3", label: "West US 3 (Arizona)", timezone: "America/Phoenix" },
  { code: "canadacentral", label: "Canada Central (Toronto)", timezone: "America/Toronto" },
  { code: "canadaeast", label: "Canada East (Quebec)", timezone: "America/Toronto" },
  { code: "brazilsouth", label: "Brazil South (São Paulo)", timezone: "America/Sao_Paulo" },
  { code: "northeurope", label: "North Europe (Ireland)", timezone: "Europe/Dublin" },
  { code: "westeurope", label: "West Europe (Netherlands)", timezone: "Europe/Amsterdam" },
  { code: "uksouth", label: "UK South (London)", timezone: "Europe/London" },
  { code: "ukwest", label: "UK West (Cardiff)", timezone: "Europe/London" },
  { code: "francecentral", label: "France Central (Paris)", timezone: "Europe/Paris" },
  { code: "germanywestcentral", label: "Germany West Central (Frankfurt)", timezone: "Europe/Berlin" },
  { code: "switzerlandnorth", label: "Switzerland North (Zurich)", timezone: "Europe/Zurich" },
  { code: "norwayeast", label: "Norway East (Oslo)", timezone: "Europe/Oslo" },
  { code: "swedencentral", label: "Sweden Central (Gävle)", timezone: "Europe/Stockholm" },
  { code: "polandcentral", label: "Poland Central (Warsaw)", timezone: "Europe/Warsaw" },
  { code: "italynorth", label: "Italy North (Milan)", timezone: "Europe/Rome" },
  { code: "spaincentral", label: "Spain Central (Madrid)", timezone: "Europe/Madrid" },
  { code: "eastasia", label: "East Asia (Hong Kong)", timezone: "Asia/Hong_Kong" },
  { code: "southeastasia", label: "Southeast Asia (Singapore)", timezone: "Asia/Singapore" },
  { code: "japaneast", label: "Japan East (Tokyo)", timezone: "Asia/Tokyo" },
  { code: "japanwest", label: "Japan West (Osaka)", timezone: "Asia/Tokyo" },
  { code: "koreacentral", label: "Korea Central (Seoul)", timezone: "Asia/Seoul" },
  { code: "centralindia", label: "Central India (Pune)", timezone: "Asia/Kolkata" },
  { code: "southindia", label: "South India (Chennai)", timezone: "Asia/Kolkata" },
  { code: "westindia", label: "West India (Mumbai)", timezone: "Asia/Kolkata" },
  { code: "australiaeast", label: "Australia East (Sydney)", timezone: "Australia/Sydney" },
  { code: "australiasoutheast", label: "Australia Southeast (Melbourne)", timezone: "Australia/Melbourne" },
  { code: "southafricanorth", label: "South Africa North (Johannesburg)", timezone: "Africa/Johannesburg" },
  { code: "uaenorth", label: "UAE North (Dubai)", timezone: "Asia/Dubai" },
  { code: "qatarcentral", label: "Qatar Central (Doha)", timezone: "Asia/Qatar" },
  { code: "israelcentral", label: "Israel Central", timezone: "Asia/Jerusalem" },
];

const GCP_REGIONS: CloudRegionSuggestion[] = [
  { code: "us-central1", label: "Iowa, United States", timezone: "America/Chicago" },
  { code: "us-east1", label: "South Carolina, United States", timezone: "America/New_York" },
  { code: "us-east4", label: "Northern Virginia, United States", timezone: "America/New_York" },
  { code: "us-east5", label: "Columbus, United States", timezone: "America/New_York" },
  { code: "us-west1", label: "Oregon, United States", timezone: "America/Los_Angeles" },
  { code: "us-west2", label: "Los Angeles, United States", timezone: "America/Los_Angeles" },
  { code: "us-west3", label: "Salt Lake City, United States", timezone: "America/Denver" },
  { code: "us-west4", label: "Las Vegas, United States", timezone: "America/Los_Angeles" },
  { code: "us-south1", label: "Dallas, United States", timezone: "America/Chicago" },
  { code: "northamerica-northeast1", label: "Montreal, Canada", timezone: "America/Toronto" },
  { code: "northamerica-northeast2", label: "Toronto, Canada", timezone: "America/Toronto" },
  { code: "southamerica-east1", label: "São Paulo, Brazil", timezone: "America/Sao_Paulo" },
  { code: "southamerica-west1", label: "Santiago, Chile", timezone: "America/Santiago" },
  { code: "europe-west1", label: "Belgium", timezone: "Europe/Brussels" },
  { code: "europe-west2", label: "London, United Kingdom", timezone: "Europe/London" },
  { code: "europe-west3", label: "Frankfurt, Germany", timezone: "Europe/Berlin" },
  { code: "europe-west4", label: "Netherlands", timezone: "Europe/Amsterdam" },
  { code: "europe-west6", label: "Zurich, Switzerland", timezone: "Europe/Zurich" },
  { code: "europe-west8", label: "Milan, Italy", timezone: "Europe/Rome" },
  { code: "europe-west9", label: "Paris, France", timezone: "Europe/Paris" },
  { code: "europe-west10", label: "Berlin, Germany", timezone: "Europe/Berlin" },
  { code: "europe-west12", label: "Turin, Italy", timezone: "Europe/Rome" },
  { code: "europe-north1", label: "Finland", timezone: "Europe/Helsinki" },
  { code: "europe-southwest1", label: "Madrid, Spain", timezone: "Europe/Madrid" },
  { code: "europe-central2", label: "Warsaw, Poland", timezone: "Europe/Warsaw" },
  { code: "asia-south1", label: "Mumbai, India", timezone: "Asia/Kolkata" },
  { code: "asia-south2", label: "Delhi, India", timezone: "Asia/Kolkata" },
  { code: "asia-southeast1", label: "Singapore", timezone: "Asia/Singapore" },
  { code: "asia-southeast2", label: "Jakarta, Indonesia", timezone: "Asia/Jakarta" },
  { code: "asia-east1", label: "Taiwan", timezone: "Asia/Taipei" },
  { code: "asia-east2", label: "Hong Kong", timezone: "Asia/Hong_Kong" },
  { code: "asia-northeast1", label: "Tokyo, Japan", timezone: "Asia/Tokyo" },
  { code: "asia-northeast2", label: "Osaka, Japan", timezone: "Asia/Tokyo" },
  { code: "asia-northeast3", label: "Seoul, South Korea", timezone: "Asia/Seoul" },
  { code: "australia-southeast1", label: "Sydney, Australia", timezone: "Australia/Sydney" },
  { code: "australia-southeast2", label: "Melbourne, Australia", timezone: "Australia/Melbourne" },
  { code: "me-central1", label: "Doha, Qatar", timezone: "Asia/Qatar" },
  { code: "me-central2", label: "Dammam, Saudi Arabia", timezone: "Asia/Riyadh" },
  { code: "me-west1", label: "Tel Aviv, Israel", timezone: "Asia/Jerusalem" },
  { code: "africa-south1", label: "Johannesburg, South Africa", timezone: "Africa/Johannesburg" },
];

// Oracle Cloud Infrastructure - keyed "oci" to match both the backend's
// real region-discovery/monitoring integration (app/integrations/providers/
// oci_provider.py, Phase 25B) and utils/cloudProviders.ts's provider value.
const OCI_REGIONS: CloudRegionSuggestion[] = [
  { code: "us-ashburn-1", label: "Ashburn, United States", timezone: "America/New_York" },
  { code: "us-phoenix-1", label: "Phoenix, United States", timezone: "America/Phoenix" },
  { code: "us-sanjose-1", label: "San Jose, United States", timezone: "America/Los_Angeles" },
  { code: "ca-toronto-1", label: "Toronto, Canada", timezone: "America/Toronto" },
  { code: "ca-montreal-1", label: "Montreal, Canada", timezone: "America/Toronto" },
  { code: "sa-saopaulo-1", label: "São Paulo, Brazil", timezone: "America/Sao_Paulo" },
  { code: "sa-vinhedo-1", label: "Vinhedo, Brazil", timezone: "America/Sao_Paulo" },
  { code: "sa-santiago-1", label: "Santiago, Chile", timezone: "America/Santiago" },
  { code: "uk-london-1", label: "London, United Kingdom", timezone: "Europe/London" },
  { code: "uk-cardiff-1", label: "Cardiff, United Kingdom", timezone: "Europe/London" },
  { code: "eu-frankfurt-1", label: "Frankfurt, Germany", timezone: "Europe/Berlin" },
  { code: "eu-amsterdam-1", label: "Amsterdam, Netherlands", timezone: "Europe/Amsterdam" },
  { code: "eu-zurich-1", label: "Zurich, Switzerland", timezone: "Europe/Zurich" },
  { code: "eu-madrid-1", label: "Madrid, Spain", timezone: "Europe/Madrid" },
  { code: "eu-marseille-1", label: "Marseille, France", timezone: "Europe/Paris" },
  { code: "eu-milan-1", label: "Milan, Italy", timezone: "Europe/Rome" },
  { code: "eu-paris-1", label: "Paris, France", timezone: "Europe/Paris" },
  { code: "eu-stockholm-1", label: "Stockholm, Sweden", timezone: "Europe/Stockholm" },
  { code: "me-jeddah-1", label: "Jeddah, Saudi Arabia", timezone: "Asia/Riyadh" },
  { code: "me-dubai-1", label: "Dubai, UAE", timezone: "Asia/Dubai" },
  { code: "me-abudhabi-1", label: "Abu Dhabi, UAE", timezone: "Asia/Dubai" },
  { code: "ap-mumbai-1", label: "Mumbai, India", timezone: "Asia/Kolkata" },
  { code: "ap-hyderabad-1", label: "Hyderabad, India", timezone: "Asia/Kolkata" },
  { code: "ap-tokyo-1", label: "Tokyo, Japan", timezone: "Asia/Tokyo" },
  { code: "ap-osaka-1", label: "Osaka, Japan", timezone: "Asia/Tokyo" },
  { code: "ap-seoul-1", label: "Seoul, South Korea", timezone: "Asia/Seoul" },
  { code: "ap-chuncheon-1", label: "Chuncheon, South Korea", timezone: "Asia/Seoul" },
  { code: "ap-singapore-1", label: "Singapore", timezone: "Asia/Singapore" },
  { code: "ap-sydney-1", label: "Sydney, Australia", timezone: "Australia/Sydney" },
  { code: "ap-melbourne-1", label: "Melbourne, Australia", timezone: "Australia/Melbourne" },
  { code: "il-jerusalem-1", label: "Jerusalem, Israel", timezone: "Asia/Jerusalem" },
  { code: "af-johannesburg-1", label: "Johannesburg, South Africa", timezone: "Africa/Johannesburg" },
];

const IBM_REGIONS: CloudRegionSuggestion[] = [
  { code: "us-south", label: "Dallas, United States", timezone: "America/Chicago" },
  { code: "us-east", label: "Washington DC, United States", timezone: "America/New_York" },
  { code: "ca-tor", label: "Toronto, Canada", timezone: "America/Toronto" },
  { code: "br-sao", label: "São Paulo, Brazil", timezone: "America/Sao_Paulo" },
  { code: "eu-gb", label: "London, United Kingdom", timezone: "Europe/London" },
  { code: "eu-de", label: "Frankfurt, Germany", timezone: "Europe/Berlin" },
  { code: "au-syd", label: "Sydney, Australia", timezone: "Australia/Sydney" },
  { code: "jp-tok", label: "Tokyo, Japan", timezone: "Asia/Tokyo" },
  { code: "jp-osa", label: "Osaka, Japan", timezone: "Asia/Tokyo" },
];

const DIGITALOCEAN_REGIONS: CloudRegionSuggestion[] = [
  { code: "nyc1", label: "New York 1, United States", timezone: "America/New_York" },
  { code: "nyc2", label: "New York 2, United States", timezone: "America/New_York" },
  { code: "nyc3", label: "New York 3, United States", timezone: "America/New_York" },
  { code: "sfo2", label: "San Francisco 2, United States", timezone: "America/Los_Angeles" },
  { code: "sfo3", label: "San Francisco 3, United States", timezone: "America/Los_Angeles" },
  { code: "tor1", label: "Toronto 1, Canada", timezone: "America/Toronto" },
  { code: "ams3", label: "Amsterdam 3, Netherlands", timezone: "Europe/Amsterdam" },
  { code: "lon1", label: "London 1, United Kingdom", timezone: "Europe/London" },
  { code: "fra1", label: "Frankfurt 1, Germany", timezone: "Europe/Berlin" },
  { code: "sgp1", label: "Singapore 1", timezone: "Asia/Singapore" },
  { code: "blr1", label: "Bangalore 1, India", timezone: "Asia/Kolkata" },
  { code: "syd1", label: "Sydney 1, Australia", timezone: "Australia/Sydney" },
];

const ALIBABA_REGIONS: CloudRegionSuggestion[] = [
  { code: "cn-hangzhou", label: "Hangzhou, China", timezone: "Asia/Shanghai" },
  { code: "cn-shanghai", label: "Shanghai, China", timezone: "Asia/Shanghai" },
  { code: "cn-beijing", label: "Beijing, China", timezone: "Asia/Shanghai" },
  { code: "cn-shenzhen", label: "Shenzhen, China", timezone: "Asia/Shanghai" },
  { code: "cn-guangzhou", label: "Guangzhou, China", timezone: "Asia/Shanghai" },
  { code: "cn-qingdao", label: "Qingdao, China", timezone: "Asia/Shanghai" },
  { code: "cn-zhangjiakou", label: "Zhangjiakou, China", timezone: "Asia/Shanghai" },
  { code: "cn-huhehaote", label: "Hohhot, China", timezone: "Asia/Shanghai" },
  { code: "cn-chengdu", label: "Chengdu, China", timezone: "Asia/Shanghai" },
  { code: "cn-hongkong", label: "Hong Kong", timezone: "Asia/Hong_Kong" },
  { code: "ap-southeast-1", label: "Singapore", timezone: "Asia/Singapore" },
  { code: "ap-southeast-2", label: "Sydney, Australia", timezone: "Australia/Sydney" },
  { code: "ap-southeast-3", label: "Kuala Lumpur, Malaysia", timezone: "Asia/Kuala_Lumpur" },
  { code: "ap-southeast-5", label: "Jakarta, Indonesia", timezone: "Asia/Jakarta" },
  { code: "ap-northeast-1", label: "Tokyo, Japan", timezone: "Asia/Tokyo" },
  { code: "ap-northeast-2", label: "Seoul, South Korea", timezone: "Asia/Seoul" },
  { code: "ap-south-1", label: "Mumbai, India", timezone: "Asia/Kolkata" },
  { code: "us-west-1", label: "Silicon Valley, United States", timezone: "America/Los_Angeles" },
  { code: "us-east-1", label: "Virginia, United States", timezone: "America/New_York" },
  { code: "eu-central-1", label: "Frankfurt, Germany", timezone: "Europe/Berlin" },
  { code: "eu-west-1", label: "London, United Kingdom", timezone: "Europe/London" },
  { code: "me-east-1", label: "Dubai, UAE", timezone: "Asia/Dubai" },
];

/** Keyed by the same lowercase provider strings this app already stores on
 * CloudProviderAccount.provider (aws/azure/gcp/oci/ibm/digitalocean/
 * alibaba). Any other value (a custom "Other" provider name, or anything
 * unrecognized) deliberately has no entry - callers must treat that as "no
 * suggestions available", not an error, and fall back to plain free-text
 * entry exactly as before. */
const REGION_SUGGESTIONS_BY_PROVIDER: Record<string, CloudRegionSuggestion[]> = {
  aws: AWS_REGIONS,
  azure: AZURE_REGIONS,
  gcp: GCP_REGIONS,
  oci: OCI_REGIONS,
  ibm: IBM_REGIONS,
  digitalocean: DIGITALOCEAN_REGIONS,
  alibaba: ALIBABA_REGIONS,
};

export function regionSuggestionsFor(provider: string): CloudRegionSuggestion[] {
  return REGION_SUGGESTIONS_BY_PROVIDER[provider.trim().toLowerCase()] ?? [];
}

export function findRegionSuggestion(provider: string, code: string): CloudRegionSuggestion | undefined {
  return regionSuggestionsFor(provider).find((r) => r.code === code);
}

// --- DST detection (Phase: Cloud Account timezone selection extension) ----
//
// Uses Intl (the browser's own IANA tzdata), never a manually-maintained
// offset table, so this is automatically correct for every zone/year the
// browser itself supports - including Southern Hemisphere zones (e.g.
// Australia/Sydney), where DST runs opposite to the Northern Hemisphere
// (summer Dec-Feb, not Jun-Aug), which a naive "is it currently between
// March and October" check would get backwards.

function offsetMinutesAt(date: Date, timeZone: string): number {
  const formatter = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "longOffset" });
  const part = formatter.formatToParts(date).find((p) => p.type === "timeZoneName")?.value ?? "GMT+00:00";
  const match = part.match(/GMT([+-])(\d{2}):(\d{2})/);
  if (!match) return 0;
  const sign = match[1] === "-" ? -1 : 1;
  return sign * (parseInt(match[2], 10) * 60 + parseInt(match[3], 10));
}

/** True if `timeZone` is currently observing Daylight Saving Time. Compares
 * today's UTC offset against the offsets on a fixed Jan 15 / Jul 15
 * reference pair for the current year: if those two differ, the zone
 * observes DST somewhere in the year, and whichever of the two is the
 * larger (clocks-forward) offset is the DST one - so "today" is in DST
 * exactly when it matches that larger offset. A zone where Jan/Jul offsets
 * are equal never observes DST at all (e.g. Asia/Kolkata, Asia/Dubai,
 * Africa/Johannesburg) and always returns false. */
export function isDstActiveNow(timeZone: string, now: Date = new Date()): boolean {
  try {
    const year = now.getUTCFullYear();
    const januaryOffset = offsetMinutesAt(new Date(Date.UTC(year, 0, 15, 12, 0, 0)), timeZone);
    const julyOffset = offsetMinutesAt(new Date(Date.UTC(year, 6, 15, 12, 0, 0)), timeZone);
    if (januaryOffset === julyOffset) return false;
    const dstOffset = Math.max(januaryOffset, julyOffset);
    return offsetMinutesAt(now, timeZone) === dstOffset;
  } catch {
    return false;
  }
}
