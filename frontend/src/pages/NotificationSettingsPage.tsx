import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert as MuiAlert,
  Box,
  Button,
  Checkbox,
  Chip,
  Divider,
  FormControlLabel,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useAuth } from "@/contexts/AuthContext";
import { authApi } from "@/services/authApi";
import { notificationSettingsApi } from "@/services/notificationSettingsApi";
import {
  SIMPLE_ALERT_CATEGORIES,
  TIERED_ALERT_CATEGORIES,
  type AlertCategory,
  type NotificationSettingUpdate,
} from "@/types";

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

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "hi", label: "Hindi" },
  { value: "pt", label: "Portuguese" },
  { value: "ja", label: "Japanese" },
  { value: "zh", label: "Chinese" },
];

const CATEGORY_LABELS: Record<AlertCategory, string> = {
  cpu: "CPU",
  memory: "Memory",
  disk: "Disk",
  network: "Network",
  storage: "Storage",
  cloud_usage: "Cloud Usage",
  cloud_cost: "Cloud Cost",
  api_latency: "API Latency",
  error_rate: "Error Rate",
  pod_restart: "Pod Restart",
  security: "Security",
  node_failure: "Node Failure",
  container_failure: "Container Failure",
  ai_prediction: "AI Prediction",
  resource_optimization: "Resource Optimization",
};

export function NotificationSettingsPage() {
  const { user, refreshCurrentUser } = useAuth();
  const queryClient = useQueryClient();

  const settingsQuery = useQuery({
    queryKey: ["notification-settings"],
    queryFn: () => notificationSettingsApi.get(),
  });

  const [form, setForm] = useState<NotificationSettingUpdate>({});
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number ?? "");
  const [fullName, setFullName] = useState(user?.full_name ?? "");

  // Seed local form state once the real settings load - re-controlling
  // directly from query data would fight the user's own edits on refetch.
  // Also used by the Cancel button to discard unsaved edits.
  const seedForm = () => {
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
      secondary_email: settingsQuery.data.secondary_email ?? "",
      country_code: settingsQuery.data.country_code ?? "",
      telegram_username: settingsQuery.data.telegram_username ?? "",
      notification_language: settingsQuery.data.notification_language,
      alert_preferences: settingsQuery.data.alert_preferences,
    });
    setPhoneNumber(user?.phone_number ?? "");
    setFullName(user?.full_name ?? "");
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(seedForm, [settingsQuery.data]);

  const set = <K extends keyof NotificationSettingUpdate>(key: K, value: NotificationSettingUpdate[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const setCategoryPreference = (category: AlertCategory, field: "enabled" | "warning" | "critical" | "saturated", value: boolean) =>
    setForm((prev) => ({
      ...prev,
      alert_preferences: {
        ...prev.alert_preferences,
        [category]: { ...prev.alert_preferences?.[category], [field]: value },
      },
    }));

  const profileMutation = useMutation({
    mutationFn: () =>
      authApi.updateMe({ full_name: fullName.trim() || null, phone_number: phoneNumber.trim() || null }),
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

      <Stack spacing={2} maxWidth={760}>
        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Contact info
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              fullWidth
              size="small"
            />
            <TextField label="Primary email" value={user?.email ?? ""} disabled fullWidth size="small" />
            <TextField
              label="Secondary email (optional)"
              placeholder="backup@example.com"
              helperText="Also receives every alert email, in addition to your primary address"
              value={form.secondary_email ?? ""}
              onChange={(e) => set("secondary_email", e.target.value)}
              fullWidth
              size="small"
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Country code"
                placeholder="+44"
                helperText="For display only"
                value={form.country_code ?? ""}
                onChange={(e) => set("country_code", e.target.value)}
                sx={{ width: 140 }}
                size="small"
              />
              <TextField
                label="Phone number"
                placeholder="+14155552671"
                helperText="E.164 format (incl. country code) - required for SMS alerts"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                fullWidth
                size="small"
              />
            </Stack>
            <TextField
              label="Telegram username (optional)"
              placeholder="@jdoe"
              helperText="Informational - Telegram delivery itself uses the chat ID below"
              value={form.telegram_username ?? ""}
              onChange={(e) => set("telegram_username", e.target.value)}
              fullWidth
              size="small"
            />
            <Box>
              <Button
                variant="outlined"
                size="small"
                loading={profileMutation.isPending}
                disabled={fullName.trim() === (user?.full_name ?? "") && phoneNumber.trim() === (user?.phone_number ?? "")}
                onClick={() => profileMutation.mutate()}
              >
                Save name &amp; phone
              </Button>
            </Box>
            <ErrorAlert error={profileMutation.error} />
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
            <TextField
              select
              label="Notification language"
              helperText="Message templates are English-only today - saved, but not yet applied"
              value={form.notification_language ?? "en"}
              onChange={(e) => set("notification_language", e.target.value)}
              size="small"
              sx={{ maxWidth: 260, mt: 1 }}
            >
              {LANGUAGES.map((lang) => (
                <MenuItem key={lang.value} value={lang.value}>
                  {lang.label}
                </MenuItem>
              ))}
            </TextField>
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

        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" gutterBottom>
            Alert type preferences
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Choose what you want to receive email/SMS/Telegram/Slack/Teams notifications for. Your
            in-app dashboard notifications above are never affected by these - only the outbound
            pings. The 60/80/90% columns apply to the tiered categories; the rest are a simple
            on/off.
          </Typography>
          <TableContainer sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Category</TableCell>
                  <TableCell align="center">Enabled</TableCell>
                  <TableCell align="center">60%</TableCell>
                  <TableCell align="center">80%</TableCell>
                  <TableCell align="center">90%</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[...TIERED_ALERT_CATEGORIES, ...SIMPLE_ALERT_CATEGORIES].map((category) => {
                  const pref = form.alert_preferences?.[category];
                  const isTiered = (TIERED_ALERT_CATEGORIES as readonly string[]).includes(category);
                  return (
                    <TableRow key={category}>
                      <TableCell>{CATEGORY_LABELS[category]}</TableCell>
                      <TableCell align="center">
                        <Checkbox
                          size="small"
                          checked={pref?.enabled ?? true}
                          onChange={(e) => setCategoryPreference(category, "enabled", e.target.checked)}
                        />
                      </TableCell>
                      {(["warning", "critical", "saturated"] as const).map((tier) => (
                        <TableCell align="center" key={tier}>
                          {isTiered && (
                            <Checkbox
                              size="small"
                              checked={pref?.[tier] ?? true}
                              onChange={(e) => setCategoryPreference(category, tier, e.target.checked)}
                            />
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        <ErrorAlert error={saveMutation.error} />
        {saveMutation.isSuccess && <MuiAlert severity="success">Saved.</MuiAlert>}

        <Stack direction="row" spacing={2}>
          <Button variant="contained" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save configuration
          </Button>
          <Button variant="outlined" onClick={seedForm}>
            Cancel
          </Button>
          <Button variant="outlined" loading={testMutation.isPending} onClick={() => testMutation.mutate()}>
            Send test notification
          </Button>
        </Stack>

        <ErrorAlert error={testMutation.error} />
        {testMutation.data && (
          <MuiAlert severity="info">
            Test result -{" "}
            {(["email", "secondary_email", "sms", "telegram", "slack"] as const)
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
