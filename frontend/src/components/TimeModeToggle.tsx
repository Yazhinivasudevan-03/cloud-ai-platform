import { ToggleButton, ToggleButtonGroup } from "@mui/material";

export type TimeDisplayMode = "utc" | "local";

// Phase 22: lets any alerts/monitoring table switch between showing UTC and
// each deployment's own configured local time, without changing what's
// actually stored (always UTC) or how tables without a configured timezone
// behave (they just show UTC either way).
export function TimeModeToggle({
  mode,
  onChange,
}: {
  mode: TimeDisplayMode;
  onChange: (mode: TimeDisplayMode) => void;
}) {
  return (
    <ToggleButtonGroup
      size="small"
      exclusive
      value={mode}
      onChange={(_, value: TimeDisplayMode | null) => value && onChange(value)}
    >
      <ToggleButton value="utc">UTC</ToggleButton>
      <ToggleButton value="local">Deployment local</ToggleButton>
    </ToggleButtonGroup>
  );
}
