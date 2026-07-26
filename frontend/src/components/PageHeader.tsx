import { Box, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { BackButton } from "@/components/BackButton";

export function PageHeader({
  title,
  subtitle,
  actions,
  hideBackButton = false,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /** Set on pages with nowhere meaningful to go back to (none currently -
   * kept as an escape hatch, e.g. for a future true landing page). */
  hideBackButton?: boolean;
}) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      justifyContent="space-between"
      alignItems={{ xs: "flex-start", sm: "center" }}
      spacing={2}
      sx={{ mb: 3 }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start" }}>
        {!hideBackButton && <BackButton />}
        <Box>
          <Typography variant="h5">{title}</Typography>
          {subtitle && (
            <Typography variant="body2" color="text.secondary">
              {subtitle}
            </Typography>
          )}
        </Box>
      </Box>
      {actions && <Box>{actions}</Box>}
    </Stack>
  );
}
