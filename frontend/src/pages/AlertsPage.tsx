import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import { Doughnut } from "react-chartjs-2";
import "@/utils/chartSetup";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusChip } from "@/components/StatusChip";
import { useAuth } from "@/contexts/AuthContext";
import { alertsApi } from "@/services/alertsApi";
import { formatDateTime } from "@/utils/formatters";
import type { Alert, AlertSeverity, AlertStatus } from "@/types";

const STATUS_OPTIONS: (AlertStatus | "")[] = ["", "active", "acknowledged", "resolved"];
const SEVERITY_OPTIONS: (AlertSeverity | "")[] = ["", "warning", "critical"];

export function AlertsPage() {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<AlertStatus | "">("active");
  const [severity, setSeverity] = useState<AlertSeverity | "">("");

  const alertsQuery = useQuery({
    queryKey: ["alerts", "global", page, pageSize, status, severity],
    queryFn: () => alertsApi.listGlobal(page, pageSize, status || undefined, severity || undefined),
  });

  // A small, real second query (not derived from the paginated table above)
  // purely for the severity breakdown chart, so the chart reflects *all*
  // active alerts, not just the current page.
  const breakdownQuery = useQuery({
    queryKey: ["alerts", "severity-breakdown"],
    queryFn: async () => {
      const [warning, critical] = await Promise.all([
        alertsApi.listGlobal(1, 1, "active", "warning"),
        alertsApi.listGlobal(1, 1, "active", "critical"),
      ]);
      return { warning: warning.meta.total, critical: critical.meta.total };
    },
  });

  const evaluateMutation = useMutation({
    mutationFn: () => alertsApi.evaluateNow(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ alertId, newStatus }: { alertId: number; newStatus: "acknowledged" | "resolved" }) =>
      alertsApi.updateStatus(alertId, newStatus),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const chartData = useMemo(
    () => ({
      labels: ["Warning", "Critical"],
      datasets: [
        {
          data: [breakdownQuery.data?.warning ?? 0, breakdownQuery.data?.critical ?? 0],
          backgroundColor: ["#ed6c02", "#d32f2f"],
        },
      ],
    }),
    [breakdownQuery.data],
  );

  const columns: DataTableColumn<Alert>[] = [
    { header: "Triggered at", render: (a) => formatDateTime(a.triggered_at) },
    { header: "Deployment", render: (a) => (a.deployment_id ? `#${a.deployment_id}` : "-") },
    { header: "Type", render: (a) => a.alert_type },
    { header: "Severity", render: (a) => <StatusChip value={a.severity} /> },
    { header: "Message", render: (a) => a.message },
    { header: "Status", render: (a) => <StatusChip value={a.status} /> },
    {
      header: "",
      align: "right",
      render: (a) =>
        hasRole("operator", "admin") && a.status !== "resolved" ? (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            {a.status === "active" && (
              <Button size="small" onClick={() => updateMutation.mutate({ alertId: a.id, newStatus: "acknowledged" })}>
                Acknowledge
              </Button>
            )}
            <Button size="small" onClick={() => updateMutation.mutate({ alertId: a.id, newStatus: "resolved" })}>
              Resolve
            </Button>
          </Stack>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle="Threshold breaches (CPU 60/80/100%), AI-flagged anomalies, and failure-risk predictions across every deployment."
        actions={
          hasRole("operator", "admin") && (
            <Button variant="contained" loading={evaluateMutation.isPending} onClick={() => evaluateMutation.mutate()}>
              Evaluate now
            </Button>
          )
        }
      />
      <ErrorAlert error={evaluateMutation.error} />

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, md: 4 }}>
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" gutterBottom>
              Active alerts by severity
            </Typography>
            <Doughnut data={chartData} />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 8 }}>
          <Paper sx={{ p: 2.5, height: "100%" }}>
            <Stack direction="row" spacing={2}>
              <TextField
                select
                label="Status"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value as AlertStatus | "");
                  setPage(1);
                }}
                sx={{ minWidth: 160 }}
              >
                {STATUS_OPTIONS.map((s) => (
                  <MenuItem key={s || "all"} value={s}>
                    {s || "All statuses"}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Severity"
                value={severity}
                onChange={(e) => {
                  setSeverity(e.target.value as AlertSeverity | "");
                  setPage(1);
                }}
                sx={{ minWidth: 160 }}
              >
                {SEVERITY_OPTIONS.map((s) => (
                  <MenuItem key={s || "all"} value={s}>
                    {s || "All severities"}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      <DataTable
        columns={columns}
        rows={alertsQuery.data?.items ?? []}
        total={alertsQuery.data?.meta.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        isLoading={alertsQuery.isLoading}
        emptyMessage="No alerts match these filters."
      />
    </>
  );
}
