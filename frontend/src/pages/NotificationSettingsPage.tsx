import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert as MuiAlert,
  Button,
  Chip,
  Divider,
  FormControlLabel,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useAuth } from "@/contexts/AuthContext";
import { authApi } from "@/services/authApi";
import { notificationSettingsApi } from "@/services/notificationSettingsApi";
import type { NotificationSettingUpdate } from "@/types";

const COMMON_TIMEZONES = [
  "UTC",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

export function NotificationSettingsPage() {
  const { user, refreshCurrentUser } = useAuth();
  const queryClient = useQueryClient();

  const settingsQuery = useQuery({
    queryKey: ["notification-settings"],
    queryFn: () => notificationSettingsApi.get(),
  });

  const [form, setForm] = useState<NotificationSettingUpdate>({});
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number ?? "");

  // Seed local form state once the real settings load - re-controlling
  // directly from query data would fight the user's own edits on refetch.
  useEffect(() => {
    if (!settingsQuery.data) return;
    setForm({
      email_enabled: settingsQuery.data.email_enabled,
      sms_enabled: settingsQuery.data.sms_enabled,
      telegram_enabled: settingsQuery.data.telegram_enabled,
      slack_enabled: settingsQuery.data.slack_enabled,
      teams_enabled: settingsQuery.data.teams_enabled,
      instant_alerts_enabled: settingsQuery.data.instant_alerts_enabled,
      daily_summary_enabled: settingsQuery.data.daily_summary_enabled,
      alert_sound_enabled: settingsQuery.data.alert_sound_enabled,
      dnd_start_time: settingsQuery.data.dnd_start_time,
      dnd_end_time: settingsQuery.data.dnd_end_time,
      timezone: settingsQuery.data.timezone,
    });
  }, [settingsQuery.data]);

  useEffect(() => {
    setPhoneNumber(user?.phone_number ?? "");
  }, [user?.phone_number]);

  const set = <K extends keyof NotificationSettingUpdate>(key: K, value: NotificationSettingUpdate[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const phoneMutation = useMutation({
    mutationFn: () => authApi.updateMe({ phone_number: phoneNumber.trim() || null }),
    onSuccess: () => void refreshCurrentUser(),
  });

  const saveMutation = useMutation({
    mutationFn: () => notificationSettingsApi.update(form),
    onSuccess: (data) => {
      queryClient.setQueryData(["notification-settings"], data);
      // Credential text fields are write-only (never echoed back) - clear
      // them after a successful save so the form doesn't imply the raw
      // secret is still sitting there.
      setForm((prev) => ({
        ...prev,
        telegram_bot_token: undefined,
        telegram_chat_id: undefined,
        slack_webhook_url: undefined,
        teams_webhook_url: undefined,
      }));
    },
  });

  const testMutation = useMutation({
    mutationFn: () => notificationSettingsApi.sendTest(),
  });

  if (!settingsQuery.data) {
    return (
      <>
        <PageHeader title="Notification Settings" subtitle="How and when you're alerted." />
        <ErrorAlert error={settingsQuery.error} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Notification Settings"
        subtitle="How and when you're alerted, per channel - see your full history on the Notifications page."
      />

      <Stack spacing={2} maxWidth={640}>
        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Contact info
          </Typography>
          <Stack spacing={2}>
            <TextField label="Email" value={user?.email ?? ""} disabled fullWidth size="small" />
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField
                label="Phone number"
                placeholder="+14155552671"
                helperText="E.164 format - required for SMS alerts"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                fullWidth
                size="small"
              />
              <Button
                variant="outlined"
                size="small"
                loading={phoneMutation.isPending}
                disabled={phoneNumber.trim() === (user?.phone_number ?? "")}
                onClick={() => phoneMutation.mutate()}
              >
                Save
              </Button>
            </Stack>
            <ErrorAlert error={phoneMutation.error} />
          </Stack>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Channels
          </Typography>
          <Stack spacing={1}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.email_enabled ?? false}
                  onChange={(e) => set("email_enabled", e.target.checked)}
                />
              }
              label="Email"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.sms_enabled ?? false}
                  onChange={(e) => set("sms_enabled", e.target.checked)}
                />
              }
              label="SMS"
            />

            <Divider sx={{ my: 1 }} />

            <FormControlLabel
              control={
                <Switch
                  checked={form.telegram_enabled ?? false}
                  onChange={(e) => set("telegram_enabled", e.target.checked)}
                />
              }
              label={
                <Stack direction="row" spacing={1} alignItems="center">
                  <span>Telegram</span>
                  {settingsQuery.data.telegram_bot_token_configured && (
                    <Chip size="small" color="success" variant="outlined" label="Bot token set" />
                  )}
                  {settingsQuery.data.telegram_chat_id_configured && (
                    <Chip size="small" color="success" variant="outlined" label="Chat ID set" />
                  )}
                </Stack>
              }
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Telegram bot token (optional - leave blank to use the shared bot)"
                placeholder={settingsQuery.data.telegram_bot_token_configured ? "•••• (set)" : ""}
                type="password"
                value={form.telegram_bot_token ?? ""}
                onChange={(e) => set("telegram_bot_token", e.target.value)}
                fullWidth
                size="small"
              />
              <TextField
                label="Your chat ID"
                placeholder={settingsQuery.data.telegram_chat_id_configured ? "•••• (set)" : ""}
                value={form.telegram_chat_id ?? ""}
                onChange={(e) => set("telegram_chat_id", e.target.value)}
                fullWidth
                size="small"
              />
            </Stack>

            <Divider sx={{ my: 1 }} />

            <FormControlLabel
              control={
                <Switch
                  checked={form.slack_enabled ?? false}
                  onChange={(e) => set("slack_enabled", e.target.checked)}
                />
              }
              label={
                <Stack direction="row" spacing={1} alignItems="center">
                  <span>Slack</span>
                  {settingsQuery.data.slack_webhook_configured && (
                    <Chip size="small" color="success" variant="outlined" label="Webhook set" />
                  )}
                </Stack>
              }
            />
            <TextField
              label="Slack webhook URL (optional - leave blank to use the shared webhook)"
              placeholder={settingsQuery.data.slack_webhook_configured ? "•••• (set)" : "https://hooks.slack.com/..."}
              type="password"
              value={form.slack_webhook_url ?? ""}
              onChange={(e) => set("slack_webhook_url", e.target.value)}
              fullWidth
              size="small"
            />

            <Divider sx={{ my: 1 }} />

            <FormControlLabel
              control={
                <Switch
                  checked={form.teams_enabled ?? false}
                  onChange={(e) => set("teams_enabled", e.target.checked)}
                />
              }
              label={
                <Stack direction="row" spacing={1} alignItems="center">
                  <span>Microsoft Teams</span>
                  {settingsQuery.data.teams_webhook_configured && (
                    <Chip size="small" color="success" variant="outlined" label="Webhook set" />
                  )}
                </Stack>
              }
            />
            <TextField
              label="Teams webhook URL"
              placeholder={settingsQuery.data.teams_webhook_configured ? "•••• (set)" : "https://outlook.office.com/webhook/..."}
              type="password"
              value={form.teams_webhook_url ?? ""}
              onChange={(e) => set("teams_webhook_url", e.target.value)}
              fullWidth
              size="small"
            />
          </Stack>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Delivery preferences
          </Typography>
          <Stack spacing={1}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.instant_alerts_enabled ?? false}
                  onChange={(e) => set("instant_alerts_enabled", e.target.checked)}
                />
              }
              label="Instant alerts (deliver as soon as triggered)"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.daily_summary_enabled ?? false}
                  onChange={(e) => set("daily_summary_enabled", e.target.checked)}
                />
              }
              label="Daily summary"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={form.alert_sound_enabled ?? false}
                  onChange={(e) => set("alert_sound_enabled", e.target.checked)}
                />
              }
              label="Play a sound for new alerts in this browser"
            />
          </Stack>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Do not disturb
          </Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            <TextField
              label="Starts at"
              type="time"
              value={(form.dnd_start_time ?? "").slice(0, 5)}
              onChange={(e) => set("dnd_start_time", e.target.value ? `${e.target.value}:00` : null)}
              InputLabelProps={{ shrink: true }}
              size="small"
            />
            <TextField
              label="Ends at"
              type="time"
              value={(form.dnd_end_time ?? "").slice(0, 5)}
              onChange={(e) => set("dnd_end_time", e.target.value ? `${e.target.value}:00` : null)}
              InputLabelProps={{ shrink: true }}
              size="small"
            />
            <TextField
              select
              label="Timezone"
              value={form.timezone ?? "UTC"}
              onChange={(e) => set("timezone", e.target.value)}
              size="small"
              sx={{ minWidth: 200 }}
            >
              {COMMON_TIMEZONES.map((tz) => (
                <MenuItem key={tz} value={tz}>
                  {tz}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
            Your in-app dashboard notifications are never suppressed - do not disturb only pauses
            email/SMS/Telegram/Slack/Teams pings.
          </Typography>
        </Paper>

        <ErrorAlert error={saveMutation.error} />
        {saveMutation.isSuccess && <MuiAlert severity="success">Saved.</MuiAlert>}

        <Stack direction="row" spacing={2}>
          <Button variant="contained" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save configuration
          </Button>
          <Button variant="outlined" loading={testMutation.isPending} onClick={() => testMutation.mutate()}>
            Send test notification
          </Button>
        </Stack>

        <ErrorAlert error={testMutation.error} />
        {testMutation.data && (
          <MuiAlert severity="info">
            Test result -{" "}
            {(["email", "sms", "telegram", "slack"] as const)
              .map((channel) => {
                const key = `${channel}_sent` as const;
                const value = testMutation.data[key];
                if (value === null) return null;
                return `${channel}: ${value ? "sent" : "not configured / failed"}`;
              })
              .filter(Boolean)
              .join(", ") || "No channels are enabled."}
          </MuiAlert>
        )}

        <Typography variant="body2">
          <Link component={RouterLink} to="/notifications">
            View your notification history
          </Link>
        </Typography>
      </Stack>
    </>
  );
}
