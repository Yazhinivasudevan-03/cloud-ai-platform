import { Chip, FormControlLabel, Paper, Stack, Switch, Typography } from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { useAuth } from "@/contexts/AuthContext";
import { useThemeMode } from "@/contexts/ThemeModeContext";

export function SettingsPage() {
  const { user } = useAuth();
  const { mode, toggleMode } = useThemeMode();

  return (
    <>
      <PageHeader title="Settings" subtitle="Your profile and display preferences." />
      <Stack spacing={2} maxWidth={480}>
        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Profile
          </Typography>
          <Stack spacing={1}>
            <Typography variant="body2">
              <strong>Username:</strong> {user?.username}
            </Typography>
            <Typography variant="body2">
              <strong>Email:</strong> {user?.email}
            </Typography>
            <Typography variant="body2">
              <strong>Full name:</strong> {user?.full_name || "-"}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">
                <strong>Roles:</strong>
              </Typography>
              {user?.roles.map((role) => (
                <Chip key={role.id} label={role.name} size="small" />
              ))}
            </Stack>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: "block" }}>
            Profile editing and password changes aren't available yet - the backend doesn't
            expose those endpoints as of Phase 6. A future phase could add them.
          </Typography>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Appearance
          </Typography>
          <FormControlLabel
            control={<Switch checked={mode === "dark"} onChange={toggleMode} />}
            label="Dark mode"
          />
        </Paper>
      </Stack>
    </>
  );
}
