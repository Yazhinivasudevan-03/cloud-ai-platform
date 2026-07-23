import { describe, expect, it } from "vitest";
import { formatCurrency, formatMegabytes, formatPercent, titleCase } from "./formatters";

describe("formatPercent", () => {
  it("formats with one decimal place by default", () => {
    expect(formatPercent(42.567)).toBe("42.6%");
  });

  it("respects a custom fraction digit count", () => {
    expect(formatPercent(42.567, 0)).toBe("43%");
  });
});

describe("formatMegabytes", () => {
  it("keeps small values in MB", () => {
    expect(formatMegabytes(512)).toBe("512 MB");
  });

  it("converts values at or above 1024 to GB", () => {
    expect(formatMegabytes(2048)).toBe("2.00 GB");
  });

  it("converts a non-round GB boundary correctly", () => {
    expect(formatMegabytes(1536)).toBe("1.50 GB");
  });
});

describe("formatCurrency", () => {
  it("formats USD by default", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
  });

  it("respects a different currency code", () => {
    expect(formatCurrency(10, "EUR")).toContain("10.00");
  });
});

describe("titleCase", () => {
  it("capitalizes each underscore-separated word", () => {
    expect(titleCase("cpu_high")).toBe("Cpu High");
  });

  it("capitalizes each space-separated word", () => {
    expect(titleCase("resolved alert")).toBe("Resolved Alert");
  });

  it("collapses mixed separators", () => {
    expect(titleCase("increase_pods recommendation")).toBe("Increase Pods Recommendation");
  });
});
