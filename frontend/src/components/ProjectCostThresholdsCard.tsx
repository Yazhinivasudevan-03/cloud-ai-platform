import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert as MuiAlert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import { ErrorAlert } from "@/components/ErrorAlert";
import { projectsApi } from "@/services/projectsApi";
import type { ProjectCostThresholdUpdate } from "@/types";

const TIER_FIELDS = ["cost_warning_threshold", "cost_critical_threshold", "cost_saturated_threshold"] as const;
const TIER_LABELS = ["Warning", "Critical", "Saturated"];

export function ProjectCostThresholdsCard({ projectId }: { projectId: number }) {
  const queryClient = useQueryClient();

  const thresholdsQuery = useQuery({
    queryKey: ["projects", projectId, "cost-thresholds"],
    queryFn: () => projectsApi.getCostThresholds(projectId),
  });

  const [form, setForm] = useState<ProjectCostThresholdUpdate>({});

  useEffect(() => {
    if (!thresholdsQuery.data) return;
    setForm({
      monthly_budget: thresholdsQuery.data.monthly_budget,
      cost_warning_threshold: thresholdsQuery.data.cost_warning_threshold,
      cost_critical_threshold: thresholdsQuery.data.cost_critical_threshold,
      cost_saturated_threshold: thresholdsQuery.data.cost_saturated_threshold,
    });
  }, [thresholdsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => projectsApi.updateCostThresholds(projectId, form),
    onSuccess: (data) => {
      queryClient.setQueryData(["projects", projectId, "cost-thresholds"], data);
    },
  });

  if (!thresholdsQuery.data) {
    return (
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" gutterBottom>
          Cost alerting
        </Typography>
        <ErrorAlert error={thresholdsQuery.error} />
      </Paper>
    );
  }

  const data = thresholdsQuery.data;

  return (
    <Paper sx={{ p: 2.5 }}>
      <Typography variant="h6" gutterBottom>
        Cost alerting
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Alerts fire off this project's actual monthly spend (summed from the billing entries
        below) against a monthly budget. No alerting happens until a budget is set.
      </Typography>

      <Stack spacing={2}>
        <TextField
          label="Monthly budget"
          type="number"
          size="small"
          value={form.monthly_budget ?? ""}
          placeholder="not set - cost alerting disabled"
          onChange={(e) =>
            setForm((prev) => ({
              ...prev,
              monthly_budget: e.target.value === "" ? null : Number(e.target.value),
            }))
          }
          sx={{ maxWidth: 260 }}
        />

        <Grid container spacing={1}>
          {TIER_FIELDS.map((field, i) => {
            const effectiveKey = `effective_${field}` as keyof typeof data;
            return (
              <Grid size={4} key={field}>
                <TextField
                  label={`${TIER_LABELS[i]} %`}
                  type="number"
                  size="small"
                  fullWidth
                  value={form[field] ?? ""}
                  placeholder={String(data[effectiveKey])}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      [field]: e.target.value === "" ? null : Number(e.target.value),
                    }))
                  }
                  slotProps={{ htmlInput: { min: 0, max: 100, step: 1 } }}
                />
              </Grid>
            );
          })}
        </Grid>
      </Stack>

      <ErrorAlert error={saveMutation.error} />
      {saveMutation.isSuccess && (
        <MuiAlert severity="success" sx={{ mt: 2 }}>
          Saved.
        </MuiAlert>
      )}

      <Button
        variant="contained"
        size="small"
        sx={{ mt: 2 }}
        loading={saveMutation.isPending}
        onClick={() => saveMutation.mutate()}
      >
        Save
      </Button>
    </Paper>
  );
}
