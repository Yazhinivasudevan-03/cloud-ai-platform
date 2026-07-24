import { Stack, Typography } from "@mui/material";
import type { TimeDisplayMode } from "@/components/TimeModeToggle";
import { formatDateTime, formatUtcLiteral } from "@/utils/formatters";
import type { Alert } from "@/types";

// Phase 22: alerts for a deployment without a configured cloud account
// timezone have no alert_time_local/deployment_timezone - this always falls
// back to the exact same UTC display as before Phase 22, regardless of which
// mode is selected, so nothing regresses for the common case.
export function AlertTimeCell({ alert, mode }: { alert: Alert; mode: TimeDisplayMode }) {
  if (mode === "local" && alert.alert_time_local) {
    return (
      <Stack>
        <Typography variant="body2">{alert.alert_time_local}</Typography>
        {alert.deployment_timezone && (
          <Typography variant="caption" color="text.secondary">
            {alert.deployment_timezone}
          </Typography>
        )}
      </Stack>
    );
  }
  return (
    <Typography variant="body2">
      {alert.alert_time_utc ? formatUtcLiteral(alert.alert_time_utc) : formatDateTime(alert.triggered_at)}
    </Typography>
  );
}
