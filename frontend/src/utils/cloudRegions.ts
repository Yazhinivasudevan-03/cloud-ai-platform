/** Curated cloud-provider region -> recommended IANA timezone tables, used
 * only to power the Region autocomplete's suggestions in
 * CloudAccountTimezoneFormDialog (extends the existing free-text Region
 * field, never replaces it - a provider with no curated table below, e.g.
 * Oracle Cloud/IBM Cloud/DigitalOcean/Alibaba Cloud, keeps today's plain
 * text entry exactly as before). The user can always override the
 * suggested timezone via the existing searchable IANA dropdown. */

export interface CloudRegionSuggestion {
  /** What actually gets stored as CloudAccountTimezone.region. */
  code: string;
  /** Human-readable city/description shown alongside the code. */
  label: string;
  /** Recommended IANA timezone identifier for this region. */
  timezone: string;
}

const AWS_REGIONS: CloudRegionSuggestion[] = [
  { code: "ap-south-1", label: "Mumbai", timezone: "Asia/Kolkata" },
  { code: "ap-south-2", label: "Hyderabad", timezone: "Asia/Kolkata" },
  { code: "ap-east-1", label: "Hong Kong", timezone: "Asia/Hong_Kong" },
  { code: "ap-southeast-1", label: "Singapore", timezone: "Asia/Singapore" },
  { code: "ap-southeast-2", label: "Sydney", timezone: "Australia/Sydney" },
  { code: "ap-southeast-3", label: "Jakarta", timezone: "Asia/Jakarta" },
  { code: "ap-southeast-4", label: "Melbourne", timezone: "Australia/Melbourne" },
  { code: "ap-northeast-1", label: "Tokyo", timezone: "Asia/Tokyo" },
  { code: "ap-northeast-2", label: "Seoul", timezone: "Asia/Seoul" },
  { code: "ap-northeast-3", label: "Osaka", timezone: "Asia/Tokyo" },
  { code: "eu-west-1", label: "Ireland", timezone: "Europe/Dublin" },
  { code: "eu-west-2", label: "London", timezone: "Europe/London" },
  { code: "eu-west-3", label: "Paris", timezone: "Europe/Paris" },
  { code: "eu-central-1", label: "Frankfurt", timezone: "Europe/Berlin" },
  { code: "eu-central-2", label: "Zurich", timezone: "Europe/Zurich" },
  { code: "eu-north-1", label: "Stockholm", timezone: "Europe/Stockholm" },
  { code: "eu-south-1", label: "Milan", timezone: "Europe/Rome" },
  { code: "eu-south-2", label: "Spain", timezone: "Europe/Madrid" },
  { code: "us-east-1", label: "N. Virginia", timezone: "America/New_York" },
  { code: "us-east-2", label: "Ohio", timezone: "America/New_York" },
  { code: "us-west-1", label: "California", timezone: "America/Los_Angeles" },
  { code: "us-west-2", label: "Oregon", timezone: "America/Los_Angeles" },
  { code: "ca-central-1", label: "Canada", timezone: "America/Toronto" },
  { code: "sa-east-1", label: "São Paulo", timezone: "America/Sao_Paulo" },
  { code: "me-south-1", label: "Bahrain", timezone: "Asia/Bahrain" },
  { code: "me-central-1", label: "UAE", timezone: "Asia/Dubai" },
  { code: "af-south-1", label: "Cape Town", timezone: "Africa/Johannesburg" },
];

const AZURE_REGIONS: CloudRegionSuggestion[] = [
  { code: "UK South", label: "UK South", timezone: "Europe/London" },
  { code: "UK West", label: "UK West", timezone: "Europe/London" },
  { code: "Central India", label: "Central India", timezone: "Asia/Kolkata" },
  { code: "South India", label: "South India", timezone: "Asia/Kolkata" },
  { code: "West Europe", label: "West Europe (Netherlands)", timezone: "Europe/Amsterdam" },
  { code: "North Europe", label: "North Europe (Ireland)", timezone: "Europe/Dublin" },
  { code: "East US", label: "East US", timezone: "America/New_York" },
  { code: "West US", label: "West US", timezone: "America/Los_Angeles" },
  { code: "Australia East", label: "Australia East (Sydney)", timezone: "Australia/Sydney" },
  { code: "Southeast Asia", label: "Southeast Asia (Singapore)", timezone: "Asia/Singapore" },
  { code: "Japan East", label: "Japan East (Tokyo)", timezone: "Asia/Tokyo" },
];

const GCP_REGIONS: CloudRegionSuggestion[] = [
  { code: "asia-south1", label: "Mumbai", timezone: "Asia/Kolkata" },
  { code: "asia-south2", label: "Delhi", timezone: "Asia/Kolkata" },
  { code: "asia-east1", label: "Taiwan", timezone: "Asia/Taipei" },
  { code: "asia-east2", label: "Hong Kong", timezone: "Asia/Hong_Kong" },
  { code: "asia-northeast1", label: "Tokyo", timezone: "Asia/Tokyo" },
  { code: "asia-northeast2", label: "Osaka", timezone: "Asia/Tokyo" },
  { code: "asia-northeast3", label: "Seoul", timezone: "Asia/Seoul" },
  { code: "asia-southeast1", label: "Singapore", timezone: "Asia/Singapore" },
  { code: "asia-southeast2", label: "Jakarta", timezone: "Asia/Jakarta" },
  { code: "australia-southeast1", label: "Sydney", timezone: "Australia/Sydney" },
  { code: "europe-west1", label: "Belgium", timezone: "Europe/Brussels" },
  { code: "europe-west2", label: "London", timezone: "Europe/London" },
  { code: "europe-west3", label: "Frankfurt", timezone: "Europe/Berlin" },
  { code: "europe-west4", label: "Netherlands", timezone: "Europe/Amsterdam" },
  { code: "europe-west8", label: "Milan", timezone: "Europe/Rome" },
  { code: "us-central1", label: "Iowa", timezone: "America/Chicago" },
  { code: "us-east1", label: "South Carolina", timezone: "America/New_York" },
  { code: "us-west1", label: "Oregon", timezone: "America/Los_Angeles" },
];

/** Keyed by the same lowercase provider strings this app already stores on
 * CloudProviderAccount.provider ("aws" | "azure" | "gcp"). Any other value
 * (oracle, ibm, digitalocean, alibaba, "other", or anything unrecognized)
 * deliberately has no entry - callers must treat that as "no suggestions
 * available", not an error. */
const REGION_SUGGESTIONS_BY_PROVIDER: Record<string, CloudRegionSuggestion[]> = {
  aws: AWS_REGIONS,
  azure: AZURE_REGIONS,
  gcp: GCP_REGIONS,
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
