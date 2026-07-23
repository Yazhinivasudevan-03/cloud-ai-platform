import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert as MuiAlert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import type { CloudAccountAlertThresholdUpdate } from "@/types";

type TierField =
  | "cpu_warning_threshold"
  | "cpu_critical_threshold"
  | "cpu_saturated_threshold"
  | "memory_warning_threshold"
  | "memory_critical_threshold"
  | "memory_saturated_threshold";

const TIER_ROWS: { metric: string; fields: [TierField, TierField, TierField] }[] = [
  {
    metric: "CPU",
    fields: ["cpu_warning_threshold", "cpu_critical_threshold", "cpu_saturated_threshold"],
  },
  {
    metric: "Memory",
    fields: ["memory_warning_threshold", "memory_critical_threshold", "memory_saturated_threshold"],
  },
];

const TIER_LABELS = ["Warning", "Critical", "Saturated"];

export function CloudAccountAlertThresholdsCard({ accountId }: { accountId: number }) {
  const queryClient = useQueryClient();

  const thresholdsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", accountId, "alert-thresholds"],
    queryFn: () => cloudProviderAccountsApi.getAlertThresholds(accountId),
  });

  const [form, setForm] = useState<CloudAccountAlertThresholdUpdate>({});

  useEffect(() => {
    if (!thresholdsQuery.data) return;
    setForm({
      cpu_warning_threshold: thresholdsQuery.data.cpu_warning_threshold,
      cpu_critical_threshold: thresholdsQuery.data.cpu_critical_threshold,
      cpu_saturated_threshold: thresholdsQuery.data.cpu_saturated_threshold,
      memory_warning_threshold: thresholdsQuery.data.memory_warning_threshold,
      memory_critical_threshold: thresholdsQuery.data.memory_critical_threshold,
      memory_saturated_threshold: thresholdsQuery.data.memory_saturated_threshold,
    });
  }, [thresholdsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => cloudProviderAccountsApi.updateAlertThresholds(accountId, form),
    onSuccess: (data) => {
      queryClient.setQueryData(["cloud-provider-accounts", accountId, "alert-thresholds"], data);
    },
  });

  if (!thresholdsQuery.data) {
    return (
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" gutterBottom>
          Alert thresholds
        </Typography>
        <ErrorAlert error={thresholdsQuery.error} />
      </Paper>
    );
  }

  const data = thresholdsQuery.data;

  return (
    <Paper sx={{ p: 2.5 }}>
      <Typography variant="h6" gutterBottom>
        Alert thresholds
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Overrides for CPU and memory alerts on deployments linked to this account. Leave a field
        blank to use the platform-wide default shown as its placeholder.
      </Typography>

      <Stack spacing={2}>
        {TIER_ROWS.map(({ metric, fields }) => (
          <Stack key={metric} spacing={1}>
            <Typography variant="subtitle2">{metric}</Typography>
            <Grid container spacing={1}>
              {fields.map((field, i) => {
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
        ))}
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
        Save thresholds
      </Button>
    </Paper>
  );
}
