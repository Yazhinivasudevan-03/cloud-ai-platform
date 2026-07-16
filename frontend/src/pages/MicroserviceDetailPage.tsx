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
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusChip } from "@/components/StatusChip";
import { microservicesApi } from "@/services/microservicesApi";
import { deploymentsApi } from "@/services/deploymentsApi";
import { useAuth } from "@/contexts/AuthContext";
import type { Deployment, DeploymentStatus } from "@/types";

const STATUS_OPTIONS: DeploymentStatus[] = ["unknown", "pending", "running", "failed"];

export function MicroserviceDetailPage() {
  const { microserviceId } = useParams();
  const id = Number(microserviceId);
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);

  const microserviceQuery = useQuery({
    queryKey: ["microservices", id],
    queryFn: () => microservicesApi.get(id),
  });
  const deploymentsQuery = useQuery({
    queryKey: ["deployments", "for-microservice", id],
    queryFn: () => deploymentsApi.listForMicroservice(id, 1, 50),
  });

  const columns: DataTableColumn<Deployment>[] = [
    {
      header: "Name",
      render: (deployment) => (
        <Typography
          variant="body2"
          fontWeight={600}
          sx={{ cursor: "pointer" }}
          onClick={() => navigate(`/deployments/${deployment.id}`)}
        >
          {deployment.name}
        </Typography>
      ),
    },
    { header: "Namespace", render: (d) => d.namespace },
    { header: "Replicas", render: (d) => d.replicas },
    { header: "Status", render: (d) => <StatusChip value={d.status} /> },
    { header: "Memory limit", render: (d) => (d.memory_limit_mb ? `${d.memory_limit_mb} MB` : "not set") },
  ];

  return (
    <>
      <PageHeader
        title={microserviceQuery.data?.name ?? "Microservice"}
        subtitle={microserviceQuery.data?.description ?? undefined}
        actions={
          hasRole("operator", "admin") && (
            <Button startIcon={<AddIcon />} variant="contained" onClick={() => setCreateOpen(true)}>
              New deployment
            </Button>
          )
        }
      />
      <DataTable
        columns={columns}
        rows={deploymentsQuery.data?.items ?? []}
        total={deploymentsQuery.data?.meta.total ?? 0}
        page={1}
        pageSize={50}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        isLoading={deploymentsQuery.isLoading}
        emptyMessage="No deployments for this microservice yet."
      />
      <CreateDeploymentDialog microserviceId={id} open={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}

function CreateDeploymentDialog({
  microserviceId,
  open,
  onClose,
}: {
  microserviceId: number;
  open: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [namespace, setNamespace] = useState("default");
  const [replicas, setReplicas] = useState("1");
  const [status, setStatus] = useState<DeploymentStatus>("unknown");
  const [memoryLimitMb, setMemoryLimitMb] = useState("");
  const [error, setError] = useState<unknown>(null);
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () =>
      deploymentsApi.create(microserviceId, {
        name,
        namespace,
        replicas: Number(replicas),
        status,
        memory_limit_mb: memoryLimitMb ? Number(memoryLimitMb) : undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["deployments", "for-microservice", microserviceId] });
      setName("");
      setNamespace("default");
      setReplicas("1");
      setStatus("unknown");
      setMemoryLimitMb("");
      onClose();
    },
    onError: setError,
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>New deployment</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={error} />
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus required fullWidth />
          <TextField label="Namespace" value={namespace} onChange={(e) => setNamespace(e.target.value)} fullWidth />
          <Box sx={{ display: "flex", gap: 2 }}>
            <TextField
              label="Replicas"
              type="number"
              value={replicas}
              onChange={(e) => setReplicas(e.target.value)}
              fullWidth
            />
            <TextField
              select
              label="Status"
              value={status}
              onChange={(e) => setStatus(e.target.value as DeploymentStatus)}
              fullWidth
            >
              {STATUS_OPTIONS.map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </TextField>
          </Box>
          <TextField
            label="Memory limit (MB, optional)"
            type="number"
            value={memoryLimitMb}
            onChange={(e) => setMemoryLimitMb(e.target.value)}
            helperText="Needed for memory-based optimization recommendations - see Phase 6"
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
