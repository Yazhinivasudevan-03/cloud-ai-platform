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
import { isDstActiveNow, regionSuggestionsFor } from "@/utils/cloudRegions";
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
  provider,
  entry,
  onClose,
}: {
  open: boolean;
  accountId: number;
  /** Drives the Region field's suggestions (see utils/cloudRegions.ts) - a
   * provider with no curated table (a custom "Other" provider name/anything
   * else unrecognized) falls back to the original plain text entry,
   * unchanged. */
  provider: string;
  entry: CloudAccountTimezone | null;
  onClose: () => void;
}) {
  const isEdit = entry !== null;
  const queryClient = useQueryClient();

  const [region, setRegion] = useState(entry?.region ?? "");
  const [availabilityZone, setAvailabilityZone] = useState(entry?.availability_zone ?? "");
  const [label, setLabel] = useState(entry?.label ?? "");
  const [timezone, setTimezone] = useState<string | null>(entry?.timezone ?? null);

  const regionSuggestions = regionSuggestionsFor(provider);
  const matchedSuggestion = regionSuggestions.find((r) => r.code === region);

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

          {regionSuggestions.length > 0 ? (
            <Autocomplete
              freeSolo
              options={regionSuggestions}
              getOptionLabel={(option) => (typeof option === "string" ? option : `${option.code} (${option.label})`)}
              isOptionEqualToValue={(option, value) =>
                typeof value === "string" ? option.code === value : option.code === value.code
              }
              value={matchedSuggestion ?? region}
              onChange={(_, newValue) => {
                if (newValue === null) {
                  setRegion("");
                } else if (typeof newValue === "string") {
                  setRegion(newValue);
                } else {
                  setRegion(newValue.code);
                  // Only auto-fill the recommended timezone if the user
                  // hasn't already picked one - never clobber a deliberate
                  // choice (e.g. when editing an existing entry).
                  if (!timezone) setTimezone(newValue.timezone);
                }
              }}
              onInputChange={(_, newInputValue, reason) => {
                if (reason === "input") setRegion(newInputValue);
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Region"
                  placeholder="e.g. eu-west-2, ap-south-1"
                  required
                  helperText={
                    matchedSuggestion ? `Recommended timezone: ${matchedSuggestion.timezone}` : undefined
                  }
                />
              )}
            />
          ) : (
            <TextField
              label="Region"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="e.g. eu-west-2, ap-south-1"
              required
              fullWidth
            />
          )}

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
              {isDstActiveNow(timezone) ? " - Daylight Saving Time is currently in effect" : ""}
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
