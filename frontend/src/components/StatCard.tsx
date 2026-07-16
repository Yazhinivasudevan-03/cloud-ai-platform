import { Paper, Stack, Typography, type SvgIconTypeMap } from "@mui/material";
import type { OverridableComponent } from "@mui/material/OverridableComponent";

export function StatCard({
  label,
  value,
  icon: Icon,
  color = "primary.main",
}: {
  label: string;
  value: string | number;
  icon: OverridableComponent<SvgIconTypeMap>;
  color?: string;
}) {
  return (
    <Paper sx={{ p: 2.5, height: "100%" }}>
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
