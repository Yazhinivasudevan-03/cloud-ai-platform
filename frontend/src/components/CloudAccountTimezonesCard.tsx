import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Button, IconButton, Paper, Stack, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/EditOutlined";
import { CloudAccountTimezoneFormDialog } from "@/components/CloudAccountTimezoneFormDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import type { CloudAccountTimezone } from "@/types";

// Phase 22: lets one cloud account track resources across multiple
// regions/timezones - e.g. the same AWS account with both an eu-west-2
// (London) and an ap-south-1 (Mumbai) deployment, each with their own
// correctly-DST-adjusted local time.
export function CloudAccountTimezonesCard({ accountId }: { accountId: number }) {
  const queryClient = useQueryClient();
  const timezonesQuery = useQuery({
    queryKey: ["cloud-provider-accounts", accountId, "timezones"],
    queryFn: () => cloudProviderAccountsApi.listTimezones(accountId),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<CloudAccountTimezone | null>(null);
  const [deletingEntry, setDeletingEntry] = useState<CloudAccountTimezone | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (entry: CloudAccountTimezone) => cloudProviderAccountsApi.deleteTimezone(accountId, entry.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "timezones"] });
      setDeletingEntry(null);
    },
  });

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">Deployment time zones</Typography>
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={() => {
            setEditingEntry(null);
            setFormOpen(true);
          }}
        >
          Add time zone
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Configure one entry per region this account has resources in. Monitoring, alerts, and
        notifications for deployments linked to an entry show local time alongside UTC.
      </Typography>

      <ErrorAlert error={timezonesQuery.error} />
      <ErrorAlert error={deleteMutation.error} />

      {timezonesQuery.data && timezonesQuery.data.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No deployment time zones configured yet for this account.
        </Typography>
      )}

      {timezonesQuery.data && timezonesQuery.data.length > 0 && (
        <Stack spacing={1.5}>
          {timezonesQuery.data.map((entry) => (
            <Paper key={entry.id} variant="outlined" sx={{ p: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap">
                <Box>
                  <Typography variant="body1" fontWeight={600}>
                    {entry.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {entry.region}
                    {entry.availability_zone ? ` (${entry.availability_zone})` : ""} - {entry.timezone}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    UTC offset {entry.utc_offset} - Local time now: {entry.current_local_time}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={0.5}>
                  <IconButton
                    size="small"
                    aria-label="Edit time zone"
                    onClick={() => {
                      setEditingEntry(entry);
                      setFormOpen(true);
                    }}
                  >
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    aria-label="Delete time zone"
                    onClick={() => setDeletingEntry(entry)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}

      {formOpen && (
        <CloudAccountTimezoneFormDialog
          open={formOpen}
          accountId={accountId}
          entry={editingEntry}
          onClose={() => setFormOpen(false)}
        />
      )}

      <ConfirmDialog
        open={deletingEntry !== null}
        title="Delete deployment time zone"
        description={`Remove the "${deletingEntry?.label ?? ""}" time zone entry? Deployments linked to it will fall back to UTC-only display.`}
        confirmLabel="Delete"
        destructive
        onConfirm={() => deletingEntry && deleteMutation.mutate(deletingEntry)}
        onCancel={() => setDeletingEntry(null)}
      />
    </Paper>
  );
}
