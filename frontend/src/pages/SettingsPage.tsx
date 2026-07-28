import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert as MuiAlert,
  Button,
  Chip,
  FormControlLabel,
  Link,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useAuth } from "@/contexts/AuthContext";
import { useThemeMode } from "@/contexts/ThemeModeContext";
import { authApi } from "@/services/authApi";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { providerLabel } from "@/utils/cloudProviders";

export function SettingsPage() {
  const { user, refreshCurrentUser } = useAuth();
  const { mode, toggleMode } = useThemeMode();

  const [firstName, setFirstName] = useState(user?.first_name ?? "");
  const [lastName, setLastName] = useState(user?.last_name ?? "");
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number ?? "");
  const [companyName, setCompanyName] = useState(user?.company_name ?? "");
  const [country, setCountry] = useState(user?.country ?? "");

  useEffect(() => {
    setFirstName(user?.first_name ?? "");
    setLastName(user?.last_name ?? "");
    setPhoneNumber(user?.phone_number ?? "");
    setCompanyName(user?.company_name ?? "");
    setCountry(user?.country ?? "");
  }, [user]);

  const profileMutation = useMutation({
    mutationFn: () =>
      authApi.updateMe({
        first_name: firstName || null,
        last_name: lastName || null,
        phone_number: phoneNumber || null,
        company_name: companyName || null,
        country: country || null,
      }),
    onSuccess: () => refreshCurrentUser(),
  });

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const passwordMutation = useMutation({
    mutationFn: () =>
      authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_new_password: confirmNewPassword,
      }),
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
    },
  });

  const cloudAccountsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", "profile-summary"],
    queryFn: () => cloudProviderAccountsApi.list({ page: 1, pageSize: 10 }),
  });

  return (
    <>
      <PageHeader title="Profile" subtitle="Your personal profile, company details, and security settings." />
      <Stack spacing={2} maxWidth={560}>
        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Profile
          </Typography>
          <Stack spacing={2}>
            <Typography variant="body2">
              <strong>Username:</strong> {user?.username}
            </Typography>
            <Typography variant="body2">
              <strong>Email:</strong> {user?.email}
            </Typography>
            <Stack direction="row" spacing={2}>
              <TextField
                label="First name"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                fullWidth
              />
              <TextField
                label="Last name"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                fullWidth
              />
            </Stack>
            <TextField
              label="Phone number"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="+14155552671"
              fullWidth
            />
            <TextField
              label="Company name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              fullWidth
            />
            <TextField
              label="Country"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              fullWidth
            />
            <ErrorAlert error={profileMutation.error} />
            {profileMutation.isSuccess && <MuiAlert severity="success">Profile updated.</MuiAlert>}
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="body2">
                <strong>Roles:</strong>
              </Typography>
              {user?.roles.map((role) => (
                <Chip key={role.id} label={role.name} size="small" />
              ))}
            </Stack>
            <Button
              variant="contained"
              sx={{ alignSelf: "flex-start" }}
              loading={profileMutation.isPending}
              onClick={() => profileMutation.mutate()}
            >
              Save profile
            </Button>
          </Stack>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Security
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="Current password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              fullWidth
            />
            <TextField
              label="New password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              helperText="At least 8 characters, with upper/lowercase and a digit"
              fullWidth
            />
            <TextField
              label="Confirm new password"
              type="password"
              value={confirmNewPassword}
              onChange={(e) => setConfirmNewPassword(e.target.value)}
              fullWidth
            />
            <ErrorAlert error={passwordMutation.error} />
            {passwordMutation.isSuccess && (
              <MuiAlert severity="success">Password changed successfully.</MuiAlert>
            )}
            <Button
              variant="contained"
              sx={{ alignSelf: "flex-start" }}
              disabled={!currentPassword || !newPassword || !confirmNewPassword}
              loading={passwordMutation.isPending}
              onClick={() => passwordMutation.mutate()}
            >
              Change password
            </Button>
          </Stack>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="h6">Connected cloud accounts</Typography>
            <Button component={RouterLink} to="/cloud-accounts" size="small">
              Manage all
            </Button>
          </Stack>
          {cloudAccountsQuery.data?.items.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No cloud accounts connected yet.
            </Typography>
          )}
          <Stack spacing={1}>
            {cloudAccountsQuery.data?.items.map((account) => (
              <Stack key={account.id} direction="row" spacing={1} alignItems="center">
                <Chip size="small" label={providerLabel(account.provider)} />
                <Typography variant="body2">{account.account_name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {account.region}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Notifications &amp; time zone
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Notification channels, alert preferences, and your display time zone are managed from{" "}
            <Link component={RouterLink} to="/notification-settings">
              Notification Settings
            </Link>
            .
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
