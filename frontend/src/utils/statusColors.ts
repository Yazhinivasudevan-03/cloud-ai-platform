import type { ChipProps } from "@mui/material";

type ChipColor = ChipProps["color"];

const COLOR_MAP: Record<string, ChipColor> = {
  // Deployment / Pod status
  running: "success",
  succeeded: "success",
  pending: "warning",
  unknown: "default",
  failed: "error",
  // Alert severity
  warning: "warning",
  critical: "error",
  // Alert / lifecycle status
  active: "error",
  acknowledged: "warning",
  resolved: "success",
  // Optimization recommendation status
  applied: "success",
  dismissed: "default",
  // Anomaly
  anomaly: "error",
  normal: "success",
};

export function statusColor(value: string): ChipColor {
  return COLOR_MAP[value.toLowerCase()] ?? "default";
}
