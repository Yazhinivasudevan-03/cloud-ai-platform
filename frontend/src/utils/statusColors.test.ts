import { describe, expect, it } from "vitest";
import { statusColor } from "./statusColors";

describe("statusColor", () => {
  it("maps known statuses to their MUI chip color", () => {
    expect(statusColor("running")).toBe("success");
    expect(statusColor("failed")).toBe("error");
    expect(statusColor("pending")).toBe("warning");
    expect(statusColor("dismissed")).toBe("default");
  });

  it("is case-insensitive", () => {
    expect(statusColor("RUNNING")).toBe("success");
    expect(statusColor("Critical")).toBe("error");
  });

  it("falls back to default for an unrecognized status", () => {
    expect(statusColor("some-new-status-nobody-mapped-yet")).toBe("default");
  });
});
