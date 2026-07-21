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
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { StatusChip } from "@/components/StatusChip";
import { CloudAccountFormDialog } from "@/components/CloudAccountFormDialog";
import { AccountUsageDialog } from "@/components/AccountUsageDialog";
import { projectsApi } from "@/services/projectsApi";
import { alertsApi } from "@/services/alertsApi";
import { optimizationApi } from "@/services/optimizationApi";
import { notificationsApi } from "@/services/notificationsApi";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatRelativeTime } from "@/utils/formatters";
import { providerLabel } from "@/utils/cloudProviders";
import { useAuth } from "@/contexts/AuthContext";
import type { CloudProviderAccount } from "@/types";

export function DashboardPage() {
  const { user } = useAuth();
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [usageAccount, setUsageAccount] = useState<CloudProviderAccount | null>(null);

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
              <Button component={RouterLink} to="/cloud-accounts" size="small">
                Manage all
              </Button>
            )}
            <Button
              size="small"
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setAddAccountOpen(true)}
            >
              Connect a cloud account
            </Button>
          </Stack>
        </Stack>

        {cloudAccountsQuery.data?.items.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            Connect an AWS, Azure, GCP, or any other cloud provider account to start monitoring its
            deployments' live CPU, memory, and network usage right here.
          </Typography>
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
                    startIcon={<MonitorHeartOutlinedIcon fontSize="small" />}
                    onClick={() => setUsageAccount(account)}
                  >
                    Usage
                  </Button>
                </Paper>
              </Grid>
            ))}
          </Grid>
        )}
      </Paper>

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

      <CloudAccountFormDialog
        open={addAccountOpen}
        account={null}
        onClose={() => setAddAccountOpen(false)}
      />
      <AccountUsageDialog account={usageAccount} onClose={() => setUsageAccount(null)} />
    </>
  );
}
