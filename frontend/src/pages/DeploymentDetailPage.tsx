import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid2";
import AddIcon from "@mui/icons-material/Add";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusChip } from "@/components/StatusChip";
import { useAuth } from "@/contexts/AuthContext";
import { deploymentsApi } from "@/services/deploymentsApi";
import { metricsApi } from "@/services/metricsApi";
import { predictionsApi } from "@/services/predictionsApi";
import { alertsApi } from "@/services/alertsApi";
import { optimizationApi } from "@/services/optimizationApi";
import { podsApi } from "@/services/podsApi";
import { formatDateTime, formatPercent } from "@/utils/formatters";
import type {
  Alert as AlertModel,
  AnomalyDetection,
  FailurePrediction,
  OptimizationRecommendation,
  Pod,
} from "@/types";

const TABS = ["Overview", "Anomalies", "Failure Risk", "Pods", "Alerts", "Optimization"];

export function DeploymentDetailPage() {
  const { deploymentId } = useParams();
  const id = Number(deploymentId);
  const [tab, setTab] = useState(0);

  const deploymentQuery = useQuery({
    queryKey: ["deployments", id],
    queryFn: () => deploymentsApi.get(id),
  });

  return (
    <>
      <PageHeader
        title={deploymentQuery.data?.name ?? "Deployment"}
        subtitle={deploymentQuery.data ? `${deploymentQuery.data.namespace} - ${deploymentQuery.data.replicas} replica(s)` : undefined}
        actions={deploymentQuery.data && <StatusChip value={deploymentQuery.data.status} />}
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable" scrollButtons="auto">
        {TABS.map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>

      {tab === 0 && <OverviewTab deploymentId={id} memoryLimitMb={deploymentQuery.data?.memory_limit_mb ?? null} />}
      {tab === 1 && <AnomaliesTab deploymentId={id} />}
      {tab === 2 && <FailureRiskTab deploymentId={id} />}
      {tab === 3 && <PodsTab deploymentId={id} />}
      {tab === 4 && <AlertsTab deploymentId={id} />}
      {tab === 5 && <OptimizationTab deploymentId={id} />}
    </>
  );
}

// --- Overview: resource usage charts + latest predictions -----------------

function OverviewTab({ deploymentId, memoryLimitMb }: { deploymentId: number; memoryLimitMb: number | null }) {
  const [ingestOpen, setIngestOpen] = useState(false);
  const { hasRole } = useAuth();

  const usageQuery = useQuery({
    queryKey: ["resource-usage", deploymentId],
    queryFn: () => metricsApi.listResourceUsage(deploymentId, 1, 100),
  });
  const predictionsQuery = useQuery({
    queryKey: ["predictions", deploymentId],
    queryFn: () => predictionsApi.listPredictions(deploymentId, 1, 10),
  });

  const chartData = useMemo(() => {
    const rows = usageQuery.data?.items ?? [];
    return [...rows]
      .reverse()
      .map((row) => ({
        time: new Date(row.recorded_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" }),
        cpu: row.cpu_usage_percent,
        memory: row.memory_usage_mb,
        memoryPercent: memoryLimitMb ? (row.memory_usage_mb / memoryLimitMb) * 100 : null,
      }));
  }, [usageQuery.data, memoryLimitMb]);

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        {hasRole("operator", "admin") && (
          <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setIngestOpen(true)}>
            Record resource usage
          </Button>
        )}
      </Box>

      {predictionsQuery.data && predictionsQuery.data.items.length > 0 && (
        <Grid container spacing={2}>
          {predictionsQuery.data.items.slice(0, 4).map((prediction) => (
            <Grid key={prediction.id} size={{ xs: 12, sm: 6, md: 3 }}>
              <Paper sx={{ p: 2 }}>
                <Typography variant="caption" color="text.secondary">
                  LSTM forecast - {prediction.metric_type}
                </Typography>
                <Typography variant="h6">{prediction.predicted_value.toFixed(1)}</Typography>
                <Chip
                  size="small"
                  label={`${formatPercent(prediction.confidence_score * 100, 0)} confidence`}
                  variant="outlined"
                />
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      <ErrorAlert error={usageQuery.error} />
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" gutterBottom>
          CPU usage (%)
        </Typography>
        {chartData.length === 0 ? (
          <EmptyChartMessage />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <RechartsTooltip />
              <Line type="monotone" dataKey="cpu" stroke="#3f6fd1" dot={false} strokeWidth={2} name="CPU %" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Paper>

      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" gutterBottom>
          Memory usage {memoryLimitMb ? "(% of limit)" : "(MB)"}
        </Typography>
        {chartData.length === 0 ? (
          <EmptyChartMessage />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={memoryLimitMb ? [0, 100] : undefined} />
              <RechartsTooltip />
              <Line
                type="monotone"
                dataKey={memoryLimitMb ? "memoryPercent" : "memory"}
                stroke="#00a884"
                dot={false}
                strokeWidth={2}
                name={memoryLimitMb ? "Memory %" : "Memory MB"}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Paper>

      <IngestResourceUsageDialog deploymentId={deploymentId} open={ingestOpen} onClose={() => setIngestOpen(false)} />
    </Stack>
  );
}

function EmptyChartMessage() {
  return (
    <Typography variant="body2" color="text.secondary" sx={{ py: 6, textAlign: "center" }}>
      No resource usage data recorded yet.
    </Typography>
  );
}

function IngestResourceUsageDialog({
  deploymentId,
  open,
  onClose,
}: {
  deploymentId: number;
  open: boolean;
  onClose: () => void;
}) {
  const [cpu, setCpu] = useState("");
  const [memory, setMemory] = useState("");
  const [disk, setDisk] = useState("");
  const [networkIn, setNetworkIn] = useState("");
  const [networkOut, setNetworkOut] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      metricsApi.ingestResourceUsage(deploymentId, {
        cpu_usage_percent: Number(cpu),
        memory_usage_mb: Number(memory),
        disk_usage_mb: Number(disk),
        network_in_kbps: Number(networkIn),
        network_out_kbps: Number(networkOut),
        recorded_at: new Date().toISOString(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["resource-usage", deploymentId] });
      setCpu("");
      setMemory("");
      setDisk("");
      setNetworkIn("");
      setNetworkOut("");
      onClose();
    },
  });

  const isValid = [cpu, memory, disk, networkIn, networkOut].every((v) => v !== "" && !Number.isNaN(Number(v)));

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Record resource usage</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={mutation.error} />
          <TextField label="CPU usage (%)" type="number" value={cpu} onChange={(e) => setCpu(e.target.value)} fullWidth />
          <TextField label="Memory usage (MB)" type="number" value={memory} onChange={(e) => setMemory(e.target.value)} fullWidth />
          <TextField label="Disk usage (MB)" type="number" value={disk} onChange={(e) => setDisk(e.target.value)} fullWidth />
          <TextField label="Network in (kbps)" type="number" value={networkIn} onChange={(e) => setNetworkIn(e.target.value)} fullWidth />
          <TextField label="Network out (kbps)" type="number" value={networkOut} onChange={(e) => setNetworkOut(e.target.value)} fullWidth />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!isValid} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// --- Anomalies --------------------------------------------------------

function AnomaliesTab({ deploymentId }: { deploymentId: number }) {
  const query = useQuery({
    queryKey: ["anomaly-detections", deploymentId],
    queryFn: () => predictionsApi.listAnomalyDetections(deploymentId, 1, 50),
  });

  const columns: DataTableColumn<AnomalyDetection>[] = [
    { header: "Detected at", render: (a) => formatDateTime(a.detected_at) },
    { header: "Metric type", render: (a) => a.metric_type },
    { header: "Anomaly score", render: (a) => a.anomaly_score.toFixed(3) },
    { header: "Flagged", render: (a) => <StatusChip value={a.is_anomaly ? "anomaly" : "normal"} /> },
  ];

  return (
    <DataTable
      columns={columns}
      rows={query.data?.items ?? []}
      total={query.data?.meta.total ?? 0}
      page={1}
      pageSize={50}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
      isLoading={query.isLoading}
      emptyMessage="No anomaly detections recorded (run the ml-models pipeline against this deployment - see docs/PHASE_4.md)."
    />
  );
}

// --- Failure risk -------------------------------------------------------

function FailureRiskTab({ deploymentId }: { deploymentId: number }) {
  const query = useQuery({
    queryKey: ["failure-predictions", deploymentId],
    queryFn: () => predictionsApi.listFailurePredictions(deploymentId, 1, 50),
  });

  const columns: DataTableColumn<FailurePrediction>[] = [
    { header: "Predicted at", render: (f) => formatDateTime(f.predicted_at) },
    { header: "Failure type", render: (f) => f.failure_type },
    { header: "Probability", render: (f) => formatPercent(f.probability * 100, 0) },
  ];

  return (
    <DataTable
      columns={columns}
      rows={query.data?.items ?? []}
      total={query.data?.meta.total ?? 0}
      page={1}
      pageSize={50}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
      isLoading={query.isLoading}
      emptyMessage="No failure predictions recorded (run the ml-models pipeline against this deployment - see docs/PHASE_4.md)."
    />
  );
}

// --- Pods ----------------------------------------------------------------

function PodsTab({ deploymentId }: { deploymentId: number }) {
  const { hasRole } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const query = useQuery({
    queryKey: ["pods", deploymentId],
    queryFn: () => podsApi.listForDeployment(deploymentId, 1, 50),
  });

  const columns: DataTableColumn<Pod>[] = [
    { header: "Pod name", render: (p) => p.pod_name },
    { header: "Node", render: (p) => p.node_name || "-" },
    { header: "Status", render: (p) => <StatusChip value={p.status} /> },
    { header: "Restarts", render: (p) => p.restart_count },
  ];

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        {hasRole("operator", "admin") && (
          <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setCreateOpen(true)}>
            Register pod
          </Button>
        )}
      </Box>
      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        total={query.data?.meta.total ?? 0}
        page={1}
        pageSize={50}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        isLoading={query.isLoading}
        emptyMessage="No pods registered for this deployment yet."
      />
      <CreatePodDialog deploymentId={deploymentId} open={createOpen} onClose={() => setCreateOpen(false)} />
    </Stack>
  );
}

function CreatePodDialog({ deploymentId, open, onClose }: { deploymentId: number; open: boolean; onClose: () => void }) {
  const [podName, setPodName] = useState("");
  const [nodeName, setNodeName] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => podsApi.create(deploymentId, { pod_name: podName, node_name: nodeName || undefined }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pods", deploymentId] });
      setPodName("");
      setNodeName("");
      onClose();
    },
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Register pod</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={mutation.error} />
          <TextField label="Pod name" value={podName} onChange={(e) => setPodName(e.target.value)} autoFocus required fullWidth />
          <TextField label="Node name" value={nodeName} onChange={(e) => setNodeName(e.target.value)} fullWidth />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!podName.trim()} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// --- Alerts ----------------------------------------------------------------

function AlertsTab({ deploymentId }: { deploymentId: number }) {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["alerts", "for-deployment", deploymentId],
    queryFn: () => alertsApi.listForDeployment(deploymentId, 1, 50),
  });

  const updateMutation = useMutation({
    mutationFn: ({ alertId, status }: { alertId: number; status: "acknowledged" | "resolved" }) =>
      alertsApi.updateStatus(alertId, status),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["alerts", "for-deployment", deploymentId] }),
  });

  const columns: DataTableColumn<AlertModel>[] = [
    { header: "Triggered at", render: (a) => formatDateTime(a.triggered_at) },
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
              <Button size="small" onClick={() => updateMutation.mutate({ alertId: a.id, status: "acknowledged" })}>
                Acknowledge
              </Button>
            )}
            <Button size="small" onClick={() => updateMutation.mutate({ alertId: a.id, status: "resolved" })}>
              Resolve
            </Button>
          </Stack>
        ) : null,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={query.data?.items ?? []}
      total={query.data?.meta.total ?? 0}
      page={1}
      pageSize={50}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
      isLoading={query.isLoading}
      emptyMessage="No alerts for this deployment."
    />
  );
}

// --- Optimization ------------------------------------------------------

function OptimizationTab({ deploymentId }: { deploymentId: number }) {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["optimization-recommendations", "for-deployment", deploymentId],
    queryFn: () => optimizationApi.listForDeployment(deploymentId, 1, 50),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "applied" | "dismissed" }) =>
      optimizationApi.updateStatus(id, status),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["optimization-recommendations", "for-deployment", deploymentId] }),
  });

  const columns: DataTableColumn<OptimizationRecommendation>[] = [
    { header: "Type", render: (r) => r.recommendation_type },
    { header: "Description", render: (r) => r.description },
    { header: "Estimated savings", render: (r) => (r.estimated_savings != null ? `$${r.estimated_savings.toFixed(2)}` : "-") },
    { header: "Status", render: (r) => <StatusChip value={r.status} /> },
    {
      header: "",
      align: "right",
      render: (r) =>
        hasRole("operator", "admin") && r.status === "pending" ? (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={() => updateMutation.mutate({ id: r.id, status: "applied" })}>
              Apply
            </Button>
            <Button size="small" onClick={() => updateMutation.mutate({ id: r.id, status: "dismissed" })}>
              Dismiss
            </Button>
          </Stack>
        ) : null,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={query.data?.items ?? []}
      total={query.data?.meta.total ?? 0}
      page={1}
      pageSize={50}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
      isLoading={query.isLoading}
      emptyMessage="No optimization recommendations for this deployment."
    />
  );
}
