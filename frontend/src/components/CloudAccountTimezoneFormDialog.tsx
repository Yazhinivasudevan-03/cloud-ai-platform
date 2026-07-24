import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { timezonesApi } from "@/services/timezonesApi";
import type { CloudAccountTimezone } from "@/types";

// Phase 22: multi-timezone support for cloud accounts. The dropdown prefers
// the browser's own IANA database (zero network round-trip, always in sync
// with the user's own runtime) and falls back to the backend's zoneinfo-based
// /timezones list (e.g. very old browsers without Intl.supportedValuesOf).
function listIanaTimezones(): string[] {
  const intlWithTimeZones = Intl as unknown as { supportedValuesOf?: (key: "timeZone") => string[] };
  try {
    return intlWithTimeZones.supportedValuesOf?.("timeZone") ?? [];
  } catch {
    return [];
  }
}

export function CloudAccountTimezoneFormDialog({
  open,
  accountId,
  entry,
  onClose,
}: {
  open: boolean;
  accountId: number;
  entry: CloudAccountTimezone | null;
  onClose: () => void;
}) {
  const isEdit = entry !== null;
  const queryClient = useQueryClient();

  const [region, setRegion] = useState(entry?.region ?? "");
  const [availabilityZone, setAvailabilityZone] = useState(entry?.availability_zone ?? "");
  const [label, setLabel] = useState(entry?.label ?? "");
  const [timezone, setTimezone] = useState<string | null>(entry?.timezone ?? null);

  const browserTimezones = listIanaTimezones();
  const backendTimezonesQuery = useQuery({
    queryKey: ["timezones"],
    queryFn: () => timezonesApi.list(),
    enabled: browserTimezones.length === 0,
    staleTime: Infinity,
  });
  const timezoneOptions = browserTimezones.length > 0 ? browserTimezones : backendTimezonesQuery.data ?? [];

  const previewQuery = useQuery({
    queryKey: ["timezones", "validate", timezone],
    queryFn: () => timezonesApi.validate(timezone as string),
    enabled: !!timezone,
  });

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        region: region.trim(),
        availability_zone: availabilityZone.trim() || null,
        label: label.trim(),
        timezone: timezone as string,
      };
      if (isEdit && entry) {
        return cloudProviderAccountsApi.updateTimezone(accountId, entry.id, payload);
      }
      return cloudProviderAccountsApi.createTimezone(accountId, payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "timezones"] });
      onClose();
    },
  });

  const canSubmit = region.trim() !== "" && label.trim() !== "" && !!timezone;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{isEdit ? "Edit deployment timezone" : "Add deployment timezone"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={mutation.error} />

          <TextField
            label="Label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. London Production"
            autoFocus
            required
            fullWidth
          />

          <TextField
            label="Region"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="e.g. eu-west-2, ap-south-1"
            required
            fullWidth
          />

          <TextField
            label="Availability zone (optional)"
            value={availabilityZone}
            onChange={(e) => setAvailabilityZone(e.target.value)}
            placeholder="e.g. eu-west-2a"
            fullWidth
          />

          <Autocomplete
            options={timezoneOptions}
            value={timezone}
            onChange={(_, newValue) => setTimezone(newValue)}
            loading={backendTimezonesQuery.isLoading}
            renderInput={(params) => (
              <TextField {...params} label="Timezone (IANA)" placeholder="e.g. Europe/London" required />
            )}
          />

          {timezone && previewQuery.data?.valid && (
            <Typography variant="caption" color="text.secondary">
              Current UTC offset: {previewQuery.data.utc_offset} - Local time now:{" "}
              {previewQuery.data.current_local_time}
            </Typography>
          )}
          {timezone && previewQuery.data && !previewQuery.data.valid && (
            <Typography variant="caption" color="error">
              {previewQuery.data.error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!canSubmit}
          loading={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {isEdit ? "Save" : "Add"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
