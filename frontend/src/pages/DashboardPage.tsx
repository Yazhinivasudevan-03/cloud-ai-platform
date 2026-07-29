import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import AddIcon from "@mui/icons-material/Add";
import CloudQueueIcon from "@mui/icons-material/CloudQueueOutlined";
import FolderIcon from "@mui/icons-material/FolderOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActiveOutlined";
import TuneIcon from "@mui/icons-material/TuneOutlined";
import MailIcon from "@mui/icons-material/MailOutlined";
import AccountCircleIcon from "@mui/icons-material/AccountCircleOutlined";
import SettingsIcon from "@mui/icons-material/SettingsOutlined";
import PeopleIcon from "@mui/icons-material/PeopleOutlined";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { StatusChip } from "@/components/StatusChip";
import { CloudAccountFormDialog } from "@/components/CloudAccountFormDialog";
import { projectsApi } from "@/services/projectsApi";
import { alertsApi } from "@/services/alertsApi";
import { optimizationApi } from "@/services/optimizationApi";
import { notificationsApi } from "@/services/notificationsApi";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatRelativeTime } from "@/utils/formatters";
import { KNOWN_PROVIDERS, providerLabel } from "@/utils/cloudProviders";
import { useAuth } from "@/contexts/AuthContext";

// The onboarding empty-state's named connect buttons - every provider a
// user can actually pick, in the order the platform first asked for them
// (AWS, Azure, Google Cloud, Oracle Cloud, IBM Cloud, DigitalOcean,
// Alibaba Cloud) - excludes the catch-all "other" entry, which stays
// reachable via the generic "Connect a cloud account" button instead.
const ONBOARDING_PROVIDERS = KNOWN_PROVIDERS.filter((p) => p.value !== "other");

export function DashboardPage() {
  const { user, hasRole } = useAuth();
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>(undefined);

  const openConnectDialog = (provider?: string) => {
    setSelectedProvider(provider);
    setAddAccountOpen(true);
  };

  const projectsQuery = useQuery({
    queryKey: ["projects", "count"],
    queryFn: () => projectsApi.list({ page: 1, pageSize: 1 }),
  });
  const cloudAccountsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", "dashboard"],
    queryFn: () => cloudProviderAccountsApi.list({ page: 1, pageSize: 10 }),
  });
  const activeAlertsQuery = useQuery({
    queryKey: ["alerts", "active-count"],
    queryFn: () => alertsApi.listGlobal(1, 5, "active"),
    refetchInterval: 60_000,
  });
  const pendingRecommendationsQuery = useQuery({
    queryKey: ["optimization-recommendations", "pending-count"],
    queryFn: () => optimizationApi.listGlobal(1, 5, "pending"),
    refetchInterval: 60_000,
  });
  const unreadNotificationsQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => notificationsApi.listMine(1, 1, false),
  });

  return (
    <>
      <PageHeader
        title={`Welcome back, ${user?.full_name || user?.username}`}
        subtitle="Here's what's happening across your monitored infrastructure."
        hideBackButton
      />

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Projects"
            value={projectsQuery.data?.meta.total ?? "-"}
            icon={FolderIcon}
            to="/projects"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Active alerts"
            value={activeAlertsQuery.data?.meta.total ?? "-"}
            icon={NotificationsActiveIcon}
            color="error.main"
            to="/alerts"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Pending recommendations"
            value={pendingRecommendationsQuery.data?.meta.total ?? "-"}
            icon={TuneIcon}
            color="warning.main"
            to="/optimization"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Unread notifications"
            value={unreadNotificationsQuery.data?.meta.total ?? "-"}
            icon={MailIcon}
            color="secondary.main"
            to="/notifications?filter=unread"
          />
        </Grid>
      </Grid>

      <Paper sx={{ p: 2.5, mb: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center">
            <CloudQueueIcon color="action" />
            <Typography variant="h6">Cloud Accounts</Typography>
          </Stack>
          <Stack direction="row" spacing={1}>
            {(cloudAccountsQuery.data?.items.length ?? 0) > 0 && (
              <>
                <Button component={RouterLink} to="/cloud-accounts" size="small">
                  Manage all
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  startIcon={<AddIcon />}
                  onClick={() => openConnectDialog()}
                >
                  Connect a cloud account
                </Button>
              </>
            )}
          </Stack>
        </Stack>

        {cloudAccountsQuery.data?.items.length === 0 && (
          <Stack spacing={2} sx={{ py: 2 }}>
            <Typography variant="body2" color="text.secondary">
              No cloud accounts connected. Connect your first cloud account to begin real-time
              monitoring.
            </Typography>
            <Grid container spacing={1.5}>
              {ONBOARDING_PROVIDERS.map((p) => (
                <Grid key={p.value} size={{ xs: 6, sm: 4, md: 3 }}>
                  <Button
                    fullWidth
                    variant="outlined"
                    startIcon={<AddIcon />}
                    onClick={() => openConnectDialog(p.value)}
                  >
                    {p.label}
                  </Button>
                </Grid>
              ))}
            </Grid>
          </Stack>
        )}

        {cloudAccountsQuery.data && cloudAccountsQuery.data.items.length > 0 && (
          <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
            {cloudAccountsQuery.data.items.map((account) => (
              <Grid key={account.id} size={{ xs: 12, sm: 6, md: 4 }}>
                <Paper
                  variant="outlined"
                  sx={{ p: 1.5, display: "flex", justifyContent: "space-between", alignItems: "center" }}
                >
                  <Stack>
                    <Typography variant="body2" fontWeight={600}>
                      {account.account_name}
                    </Typography>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      <Chip size="small" label={providerLabel(account.provider)} />
                      <Typography variant="caption" color="text.secondary">
                        {account.region}
                      </Typography>
                    </Stack>
                  </Stack>
                  <Button
                    size="small"
                    component={RouterLink}
                    to={`/cloud-accounts/${account.id}`}
                    startIcon={<MonitorHeartOutlinedIcon fontSize="small" />}
                  >
                    Monitor
                  </Button>
                </Paper>
              </Grid>
            ))}
          </Grid>
        )}
      </Paper>

      {(cloudAccountsQuery.data?.items.length ?? 0) > 0 && (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper sx={{ p: 2.5 }}>
              <Typography variant="h6" gutterBottom>
                Recent alerts
              </Typography>
              <Stack spacing={1.5}>
                {activeAlertsQuery.data?.items.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    No active alerts right now.
                  </Typography>
                )}
                {activeAlertsQuery.data?.items.map((alert) => (
                  <Stack key={alert.id} direction="row" justifyContent="space-between" alignItems="center">
                    <Stack>
                      <Typography variant="body2">{alert.message}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        Deployment #{alert.deployment_id} - {formatRelativeTime(alert.triggered_at)}
                      </Typography>
                    </Stack>
                    <StatusChip value={alert.severity} />
                  </Stack>
                ))}
              </Stack>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Paper sx={{ p: 2.5 }}>
              <Typography variant="h6" gutterBottom>
                Recent optimization recommendations
              </Typography>
              <Stack spacing={1.5}>
                {pendingRecommendationsQuery.data?.items.length === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    No pending recommendations.
                  </Typography>
                )}
                {pendingRecommendationsQuery.data?.items.map((recommendation) => (
                  <Stack key={recommendation.id}>
                    <Typography variant="body2">{recommendation.description}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Deployment #{recommendation.deployment_id} - {recommendation.recommendation_type}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Paper>
          </Grid>
        </Grid>
      )}

      <Paper sx={{ p: 2.5, mt: 3 }}>
        <Typography variant="h6" gutterBottom>
          Account
        </Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
          <Button component={RouterLink} to="/profile" variant="outlined" startIcon={<AccountCircleIcon />}>
            Profile
          </Button>
          <Button component={RouterLink} to="/settings" variant="outlined" startIcon={<SettingsIcon />}>
            Settings
          </Button>
          <Button
            component={RouterLink}
            to="/notification-settings"
            variant="outlined"
            startIcon={<NotificationsActiveIcon />}
          >
            Notification Settings
          </Button>
          {hasRole("admin") && (
            <Button component={RouterLink} to="/users" variant="outlined" startIcon={<PeopleIcon />}>
              Manage Users
            </Button>
          )}
        </Stack>
      </Paper>

      <CloudAccountFormDialog
        key={selectedProvider ?? "none"}
        open={addAccountOpen}
        account={null}
        initialProvider={selectedProvider}
        onClose={() => setAddAccountOpen(false)}
      />
    </>
  );
}
