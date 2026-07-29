import { describe, expect, it } from "vitest";
import { findRegionSuggestion, isDstActiveNow, regionSuggestionsFor } from "./cloudRegions";

// Intl.supportedValuesOf("timeZone") only lists each zone's *canonical*
// name per this runtime's bundled ICU data - some real, fully-functional
// IANA identifiers are "link" aliases to a canonical name that can differ
// across Node/browser/ICU versions (e.g. this Node considers "Asia/Calcutta"
// canonical and "Asia/Kolkata" - the identifier this app's backend/tests and
// the original request both use - an alias). Constructing a DateTimeFormat
// is the correct way to check "is this usable as an IANA timezone", since
// it accepts aliases too, matching how the rest of this app (and the
// backend's own zoneinfo-based validation) actually treats these values.
function isUsableIanaTimezone(timeZone: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone });
    return true;
  } catch {
    return false;
  }
}

describe("regionSuggestionsFor", () => {
  it("returns the AWS region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("aws");
    expect(regions.length).toBeGreaterThan(20);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("returns the Azure region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("azure");
    expect(regions.length).toBeGreaterThan(20);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("returns the GCP region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("gcp");
    expect(regions.length).toBeGreaterThan(20);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("returns the OCI region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("oci");
    expect(regions.length).toBeGreaterThan(10);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("returns the IBM Cloud region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("ibm");
    expect(regions.length).toBeGreaterThan(3);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("returns the DigitalOcean region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("digitalocean");
    expect(regions.length).toBeGreaterThan(3);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("returns the Alibaba Cloud region table with every timezone a real IANA identifier", () => {
    const regions = regionSuggestionsFor("alibaba");
    expect(regions.length).toBeGreaterThan(10);
    for (const region of regions) {
      expect(isUsableIanaTimezone(region.timezone)).toBe(true);
    }
  });

  it("is case-insensitive", () => {
    expect(regionSuggestionsFor("AWS")).toEqual(regionSuggestionsFor("aws"));
    expect(regionSuggestionsFor("  Azure ")).toEqual(regionSuggestionsFor("azure"));
  });

  it("returns an empty list for providers with no curated table (not an error)", () => {
    // "oracle" deliberately has no entry - the real key is "oci" (matching
    // the backend's provider_factory registry and the official OCI SDK/CLI
    // naming convention), so a stale/mistyped provider string still falls
    // back to plain free-text entry rather than erroring.
    expect(regionSuggestionsFor("oracle")).toEqual([]);
    expect(regionSuggestionsFor("other")).toEqual([]);
    expect(regionSuggestionsFor("")).toEqual([]);
  });

  it.each([
    ["ap-south-1", "Asia/Kolkata"],
    ["ap-east-1", "Asia/Hong_Kong"],
    ["ap-southeast-2", "Australia/Sydney"],
    ["ap-southeast-4", "Australia/Melbourne"],
    ["ap-northeast-3", "Asia/Tokyo"],
    ["eu-west-1", "Europe/Dublin"],
    ["eu-central-1", "Europe/Berlin"],
    ["eu-south-1", "Europe/Rome"],
    ["us-east-1", "America/New_York"],
    ["us-west-2", "America/Los_Angeles"],
    ["ca-central-1", "America/Toronto"],
    ["sa-east-1", "America/Sao_Paulo"],
    ["me-central-1", "Asia/Dubai"],
    ["af-south-1", "Africa/Johannesburg"],
  ])("AWS %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("aws", code)?.timezone).toBe(timezone);
  });

  it.each([
    ["uksouth", "Europe/London"],
    ["centralindia", "Asia/Kolkata"],
    ["westeurope", "Europe/Amsterdam"],
    ["northeurope", "Europe/Dublin"],
    ["australiaeast", "Australia/Sydney"],
    ["japaneast", "Asia/Tokyo"],
  ])("Azure %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("azure", code)?.timezone).toBe(timezone);
  });

  it.each([
    ["asia-south1", "Asia/Kolkata"],
    ["asia-east1", "Asia/Taipei"],
    ["asia-northeast1", "Asia/Tokyo"],
    ["australia-southeast1", "Australia/Sydney"],
    ["europe-west1", "Europe/Brussels"],
    ["us-central1", "America/Chicago"],
    ["us-east1", "America/New_York"],
  ])("GCP %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("gcp", code)?.timezone).toBe(timezone);
  });

  it.each([
    ["us-ashburn-1", "America/New_York"],
    ["uk-london-1", "Europe/London"],
    ["ap-mumbai-1", "Asia/Kolkata"],
    ["ap-sydney-1", "Australia/Sydney"],
  ])("OCI %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("oci", code)?.timezone).toBe(timezone);
  });

  it.each([
    ["us-south", "America/Chicago"],
    ["eu-gb", "Europe/London"],
    ["jp-tok", "Asia/Tokyo"],
  ])("IBM Cloud %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("ibm", code)?.timezone).toBe(timezone);
  });

  it.each([
    ["nyc1", "America/New_York"],
    ["lon1", "Europe/London"],
    ["sgp1", "Asia/Singapore"],
  ])("DigitalOcean %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("digitalocean", code)?.timezone).toBe(timezone);
  });

  it.each([
    ["cn-hangzhou", "Asia/Shanghai"],
    ["ap-southeast-1", "Asia/Singapore"],
    ["eu-central-1", "Europe/Berlin"],
  ])("Alibaba Cloud %s maps to %s", (code, timezone) => {
    expect(findRegionSuggestion("alibaba", code)?.timezone).toBe(timezone);
  });
});

describe("isDstActiveNow", () => {
  it("is true for Europe/London in July (BST)", () => {
    expect(isDstActiveNow("Europe/London", new Date("2026-07-15T12:00:00Z"))).toBe(true);
  });

  it("is false for Europe/London in January (GMT)", () => {
    expect(isDstActiveNow("Europe/London", new Date("2026-01-15T12:00:00Z"))).toBe(false);
  });

  it("is never true for Asia/Kolkata (India does not observe DST)", () => {
    expect(isDstActiveNow("Asia/Kolkata", new Date("2026-07-15T12:00:00Z"))).toBe(false);
    expect(isDstActiveNow("Asia/Kolkata", new Date("2026-01-15T12:00:00Z"))).toBe(false);
  });

  it("is never true for Asia/Dubai (UAE does not observe DST)", () => {
    expect(isDstActiveNow("Asia/Dubai", new Date("2026-07-15T12:00:00Z"))).toBe(false);
  });

  it("correctly handles the Southern Hemisphere (Australia/Sydney: DST in local summer, Dec-Mar)", () => {
    // A naive "DST is active March-October" check would get this backwards.
    expect(isDstActiveNow("Australia/Sydney", new Date("2026-01-15T12:00:00Z"))).toBe(true);
    expect(isDstActiveNow("Australia/Sydney", new Date("2026-07-15T12:00:00Z"))).toBe(false);
  });
});
