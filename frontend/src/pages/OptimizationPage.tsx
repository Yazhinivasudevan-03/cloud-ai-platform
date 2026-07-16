import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, MenuItem, Stack, TextField } from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusChip } from "@/components/StatusChip";
import { useAuth } from "@/contexts/AuthContext";
import { optimizationApi } from "@/services/optimizationApi";
import { formatDateTime } from "@/utils/formatters";
import type { OptimizationRecommendation, OptimizationRecommendationStatus } from "@/types";

const STATUS_OPTIONS: (OptimizationRecommendationStatus | "")[] = ["", "pending", "applied", "dismissed"];
const TYPE_OPTIONS = [
  "",
  "increase_cpu",
  "reduce_cpu",
  "increase_memory",
  "reduce_memory",
  "increase_pods",
  "reduce_pods",
  "scale_deployment",
  "optimize_cost",
];

export function OptimizationPage() {
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<OptimizationRecommendationStatus | "">("pending");
  const [recommendationType, setRecommendationType] = useState("");

  const query = useQuery({
    queryKey: ["optimization-recommendations", "global", page, pageSize, status, recommendationType],
    queryFn: () => optimizationApi.listGlobal(page, pageSize, status || undefined, recommendationType || undefined),
  });

  const evaluateMutation = useMutation({
    mutationFn: () => optimizationApi.evaluateNow(),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["optimization-recommendations"] }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, newStatus }: { id: number; newStatus: "applied" | "dismissed" }) =>
      optimizationApi.updateStatus(id, newStatus),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["optimization-recommendations"] }),
  });

  const columns: DataTableColumn<OptimizationRecommendation>[] = [
    { header: "Created", render: (r) => formatDateTime(r.created_at) },
    { header: "Deployment", render: (r) => `#${r.deployment_id}` },
    { header: "Type", render: (r) => r.recommendation_type },
    { header: "Description", render: (r) => r.description },
    { header: "Est. savings", render: (r) => (r.estimated_savings != null ? `$${r.estimated_savings.toFixed(2)}` : "-") },
    { header: "Status", render: (r) => <StatusChip value={r.status} /> },
    {
      header: "",
      align: "right",
      render: (r) =>
        hasRole("operator", "admin") && r.status === "pending" ? (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" onClick={() => updateMutation.mutate({ id: r.id, newStatus: "applied" })}>
              Apply
            </Button>
            <Button size="small" onClick={() => updateMutation.mutate({ id: r.id, newStatus: "dismissed" })}>
              Dismiss
            </Button>
          </Stack>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title="Resource Optimization"
        subtitle="Rule-based recommendations (CPU/memory/pod sizing, HPA-style scaling, cost) across every deployment."
        actions={
          hasRole("operator", "admin") && (
            <Button variant="contained" loading={evaluateMutation.isPending} onClick={() => evaluateMutation.mutate()}>
              Evaluate now
            </Button>
          )
        }
      />
      <ErrorAlert error={evaluateMutation.error} />

      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as OptimizationRecommendationStatus | "");
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
          label="Type"
          value={recommendationType}
          onChange={(e) => {
            setRecommendationType(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 200 }}
        >
          {TYPE_OPTIONS.map((t) => (
            <MenuItem key={t || "all"} value={t}>
              {t || "All types"}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        total={query.data?.meta.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        isLoading={query.isLoading}
        emptyMessage="No optimization recommendations match these filters."
      />
    </>
  );
}
