import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid2";
import AddIcon from "@mui/icons-material/Add";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { microservicesApi } from "@/services/microservicesApi";
import { projectsApi } from "@/services/projectsApi";
import { cloudCostsApi } from "@/services/cloudCostsApi";
import { formatCurrency, formatDateTime } from "@/utils/formatters";
import { useAuth } from "@/contexts/AuthContext";
import type { CloudCost, Microservice } from "@/types";

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const [tab, setTab] = useState(0);
  const [createMicroserviceOpen, setCreateMicroserviceOpen] = useState(false);
  const [ingestCostOpen, setIngestCostOpen] = useState(false);

  const projectQuery = useQuery({
    queryKey: ["projects", id],
    queryFn: () => projectsApi.get(id),
  });
  const microservicesQuery = useQuery({
    queryKey: ["microservices", "for-project", id],
    queryFn: () => microservicesApi.listForProject(id, 1, 50),
  });
  const cloudCostsQuery = useQuery({
    queryKey: ["cloud-costs", id],
    queryFn: () => cloudCostsApi.listForProject(id, 1, 50),
  });
  const forecastQuery = useQuery({
    queryKey: ["cost-forecast", id],
    queryFn: () => cloudCostsApi.forecast(id),
    retry: false,
  });

  const microserviceColumns: DataTableColumn<Microservice>[] = [
    {
      header: "Name",
      render: (ms) => (
        <Typography
          variant="body2"
          fontWeight={600}
          sx={{ cursor: "pointer" }}
          onClick={() => navigate(`/microservices/${ms.id}`)}
        >
          {ms.name}
        </Typography>
      ),
    },
    { header: "Language", render: (ms) => ms.language || "-" },
    { header: "Repository", render: (ms) => ms.repository_url || "-" },
    { header: "Created", render: (ms) => formatDateTime(ms.created_at) },
  ];

  const costColumns: DataTableColumn<CloudCost>[] = [
    { header: "Provider", render: (c) => c.provider },
    { header: "Service", render: (c) => c.service_name },
    { header: "Amount", render: (c) => formatCurrency(c.cost_amount, c.currency) },
    { header: "Period", render: (c) => `${c.billing_period_start} to ${c.billing_period_end}` },
  ];

  return (
    <>
      <PageHeader
        title={projectQuery.data?.name ?? "Project"}
        subtitle={projectQuery.data?.description ?? undefined}
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Microservices" />
        <Tab label="Cloud Costs" />
      </Tabs>

      {tab === 0 && (
        <>
          <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
            {hasRole("operator", "admin") && (
              <Button startIcon={<AddIcon />} variant="contained" onClick={() => setCreateMicroserviceOpen(true)}>
                New microservice
              </Button>
            )}
          </Box>
          <DataTable
            columns={microserviceColumns}
            rows={microservicesQuery.data?.items ?? []}
            total={microservicesQuery.data?.meta.total ?? 0}
            page={1}
            pageSize={50}
            onPageChange={() => {}}
            onPageSizeChange={() => {}}
            isLoading={microservicesQuery.isLoading}
            emptyMessage="No microservices in this project yet."
          />
        </>
      )}

      {tab === 1 && (
        <Stack spacing={2}>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 5 }}>
              <Paper sx={{ p: 2.5 }}>
                <Typography variant="h6" gutterBottom>
                  Next month forecast
                </Typography>
                {forecastQuery.isError && (
                  <Typography variant="body2" color="text.secondary">
                    Not enough billing history yet to forecast.
                  </Typography>
                )}
                {forecastQuery.data && (
                  <Stack spacing={0.5}>
                    <Typography variant="h4">
                      {formatCurrency(forecastQuery.data.predicted_next_month_cost, forecastQuery.data.currency)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Method: {forecastQuery.data.method.replace("_", " ")} - based on{" "}
                      {forecastQuery.data.historical_periods_used} historical period(s)
                      {forecastQuery.data.trend_slope_per_month !== null &&
                        ` - trend ${forecastQuery.data.trend_slope_per_month >= 0 ? "+" : ""}${formatCurrency(
                          forecastQuery.data.trend_slope_per_month,
                          forecastQuery.data.currency,
                        )}/month`}
                    </Typography>
                  </Stack>
                )}
              </Paper>
            </Grid>
            <Grid size={{ xs: 12, md: 7 }}>
              <Box sx={{ display: "flex", justifyContent: "flex-end", height: "100%", alignItems: "flex-start" }}>
                {hasRole("operator", "admin") && (
                  <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setIngestCostOpen(true)}>
                    Record billing entry
                  </Button>
                )}
              </Box>
            </Grid>
          </Grid>
          <DataTable
            columns={costColumns}
            rows={cloudCostsQuery.data?.items ?? []}
            total={cloudCostsQuery.data?.meta.total ?? 0}
            page={1}
            pageSize={50}
            onPageChange={() => {}}
            onPageSizeChange={() => {}}
            isLoading={cloudCostsQuery.isLoading}
            emptyMessage="No billing entries recorded for this project yet."
          />
        </Stack>
      )}

      <CreateMicroserviceDialog
        projectId={id}
        open={createMicroserviceOpen}
        onClose={() => setCreateMicroserviceOpen(false)}
      />
      <IngestCloudCostDialog projectId={id} open={ingestCostOpen} onClose={() => setIngestCostOpen(false)} />
    </>
  );
}

function CreateMicroserviceDialog({
  projectId,
  open,
  onClose,
}: {
  projectId: number;
  open: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      microservicesApi.create(projectId, {
        name,
        language: language || undefined,
        repository_url: repositoryUrl || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["microservices", "for-project", projectId] });
      setName("");
      setLanguage("");
      setRepositoryUrl("");
      onClose();
    },
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>New microservice</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={createMutation.error} />
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus required fullWidth />
          <TextField label="Language" value={language} onChange={(e) => setLanguage(e.target.value)} fullWidth />
          <TextField
            label="Repository URL"
            value={repositoryUrl}
            onChange={(e) => setRepositoryUrl(e.target.value)}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!name.trim()} loading={createMutation.isPending} onClick={() => createMutation.mutate()}>
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}

const PROVIDERS = ["aws", "azure", "gcp", "on_prem"];

function IngestCloudCostDialog({
  projectId,
  open,
  onClose,
}: {
  projectId: number;
  open: boolean;
  onClose: () => void;
}) {
  const [provider, setProvider] = useState("aws");
  const [serviceName, setServiceName] = useState("");
  const [costAmount, setCostAmount] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const queryClient = useQueryClient();

  const ingestMutation = useMutation({
    mutationFn: () =>
      cloudCostsApi.ingest(projectId, {
        provider,
        service_name: serviceName,
        cost_amount: Number(costAmount),
        billing_period_start: periodStart,
        billing_period_end: periodEnd,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-costs", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["cost-forecast", projectId] });
      setServiceName("");
      setCostAmount("");
      setPeriodStart("");
      setPeriodEnd("");
      onClose();
    },
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Record billing entry</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={ingestMutation.error} />
          <TextField select label="Provider" value={provider} onChange={(e) => setProvider(e.target.value)} fullWidth>
            {PROVIDERS.map((p) => (
              <MenuItem key={p} value={p}>
                {p}
              </MenuItem>
            ))}
          </TextField>
          <TextField label="Service name" value={serviceName} onChange={(e) => setServiceName(e.target.value)} required fullWidth />
          <TextField
            label="Cost amount"
            type="number"
            value={costAmount}
            onChange={(e) => setCostAmount(e.target.value)}
            required
            fullWidth
          />
          <TextField
            label="Billing period start"
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            required
            fullWidth
          />
          <TextField
            label="Billing period end"
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            required
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!serviceName.trim() || !costAmount || !periodStart || !periodEnd}
          loading={ingestMutation.isPending}
          onClick={() => ingestMutation.mutate()}
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
