import { Link as RouterLink } from "react-router-dom";
import { Paper, Stack, Typography, type SvgIconTypeMap } from "@mui/material";
import type { OverridableComponent } from "@mui/material/OverridableComponent";

export function StatCard({
  label,
  value,
  icon: Icon,
  color = "primary.main",
  to,
}: {
  label: string;
  value: string | number;
  icon: OverridableComponent<SvgIconTypeMap>;
  color?: string;
  /** If provided, the whole card becomes a link to this route. */
  to?: string;
}) {
  return (
    <Paper
      {...(to ? { component: RouterLink, to } : {})}
      sx={{
        p: 2.5,
        height: "100%",
        display: "block",
        textDecoration: "none",
        color: "inherit",
        ...(to
          ? {
              cursor: "pointer",
              transition: "background-color 0.15s, border-color 0.15s",
              "&:hover": {
                bgcolor: (theme) => theme.palette.action.hover,
                borderColor: (theme) => theme.palette.primary.main,
              },
            }
          : {}),
      }}
    >
      <Stack direction="row" spacing={2} alignItems="center">
        <Stack
          alignItems="center"
          justifyContent="center"
          sx={{
            width: 48,
            height: 48,
            borderRadius: 2,
            bgcolor: (theme) => theme.palette.action.hover,
            color,
          }}
        >
          <Icon />
        </Stack>
        <Stack>
          <Typography variant="h5" fontWeight={700}>
            {value}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}
