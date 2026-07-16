import { useQuery } from "@tanstack/react-query";
import { Paper, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import FolderIcon from "@mui/icons-material/FolderOutlined";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActiveOutlined";
import TuneIcon from "@mui/icons-material/TuneOutlined";
import MailIcon from "@mui/icons-material/MailOutlined";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { StatusChip } from "@/components/StatusChip";
import { projectsApi } from "@/services/projectsApi";
import { alertsApi } from "@/services/alertsApi";
import { optimizationApi } from "@/services/optimizationApi";
import { notificationsApi } from "@/services/notificationsApi";
import { formatRelativeTime } from "@/utils/formatters";
import { useAuth } from "@/contexts/AuthContext";

export function DashboardPage() {
  const { user } = useAuth();

  const projectsQuery = useQuery({
    queryKey: ["projects", "count"],
    queryFn: () => projectsApi.list({ page: 1, pageSize: 1 }),
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
          <StatCard label="Projects" value={projectsQuery.data?.meta.total ?? "-"} icon={FolderIcon} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Active alerts"
            value={activeAlertsQuery.data?.meta.total ?? "-"}
            icon={NotificationsActiveIcon}
            color="error.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Pending recommendations"
            value={pendingRecommendationsQuery.data?.meta.total ?? "-"}
            icon={TuneIcon}
            color="warning.main"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Unread notifications"
            value={unreadNotificationsQuery.data?.meta.total ?? "-"}
            icon={MailIcon}
            color="secondary.main"
          />
        </Grid>
      </Grid>

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
    </>
  );
}
