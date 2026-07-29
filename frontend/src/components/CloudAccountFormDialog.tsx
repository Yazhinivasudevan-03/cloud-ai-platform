import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { KNOWN_PROVIDERS } from "@/utils/cloudProviders";
import { regionSuggestionsFor } from "@/utils/cloudRegions";
import type { CloudProviderAccount } from "@/types";

interface CredentialField {
  key: string;
  value: string;
}

export function CloudAccountFormDialog({
  open,
  account,
  onClose,
  initialProvider,
}: {
  open: boolean;
  account: CloudProviderAccount | null;
  onClose: () => void;
  /** Preselects the Provider field (e.g. from a "Connect AWS" button) -
   * only used for a new account, never overrides an existing one being edited. */
  initialProvider?: string;
}) {
  const isEdit = account !== null;
  const queryClient = useQueryClient();

  const [provider, setProvider] = useState(account?.provider ?? initialProvider ?? "aws");
  const [customProvider, setCustomProvider] = useState(
    account && !KNOWN_PROVIDERS.some((p) => p.value === account.provider) ? account.provider : ""
  );
  const [accountName, setAccountName] = useState(account?.account_name ?? "");
  const [region, setRegion] = useState(account?.region ?? "");
  const [accountIdentifier, setAccountIdentifier] = useState(account?.account_identifier ?? "");
  // Credentials are write-only server-side (never returned by GET), so on
  // edit this always starts empty - leaving every row blank means "keep the
  // existing stored credentials unchanged" (only non-empty rows are sent).
  const [credentialFields, setCredentialFields] = useState<CredentialField[]>([{ key: "", value: "" }]);

  const resolvedProvider = provider === "other" ? customProvider.trim() : provider;

  // Searchable region suggestions (utils/cloudRegions.ts, the same central
  // catalog CloudAccountTimezoneFormDialog already uses) - a provider with
  // no curated table (a custom "Other" provider) falls back to today's
  // plain free-text Region field, unchanged.
  const regionSuggestions = regionSuggestionsFor(resolvedProvider);
  const matchedSuggestion = regionSuggestions.find((r) => r.code === region);

  const mutation = useMutation({
    mutationFn: () => {
      const credentials = Object.fromEntries(
        credentialFields
          .filter((f) => f.key.trim() !== "" && f.value.trim() !== "")
          .map((f) => [f.key.trim(), f.value])
      );
      const basePayload = {
        provider: resolvedProvider,
        account_name: accountName.trim(),
        region: region.trim(),
        account_identifier: accountIdentifier.trim() || undefined,
      };
      if (isEdit && account) {
        return cloudProviderAccountsApi.update(account.id, {
          ...basePayload,
          ...(Object.keys(credentials).length > 0 ? { credentials } : {}),
        });
      }
      return cloudProviderAccountsApi.create({ ...basePayload, credentials });
    },
    onSuccess: (savedAccount) => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts"] });

      // Automatically associates the selected region's recommended IANA
      // timezone (see utils/cloudRegions.ts) so monitoring/dashboards/
      // alerts/notifications for deployments linked to this account can
      // show local time (Phase 22's existing CloudAccountTimezone feature)
      // without the user having to add it by hand. Best-effort only - a
      // duplicate (e.g. re-saving the same region on edit) or any other
      // failure here must never block the account connect/save itself,
      // which has already succeeded by this point.
      if (matchedSuggestion) {
        cloudProviderAccountsApi
          .createTimezone(savedAccount.id, {
            region: matchedSuggestion.code,
            label: matchedSuggestion.label,
            timezone: matchedSuggestion.timezone,
          })
          .catch(() => {});
      }

      onClose();
    },
  });

  const canSubmit =
    accountName.trim() !== "" &&
    region.trim() !== "" &&
    resolvedProvider !== "" &&
    (isEdit || credentialFields.some((f) => f.key.trim() !== "" && f.value.trim() !== ""));

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{isEdit ? "Edit cloud account" : "Add cloud account"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={mutation.error} />

          <TextField
            select
            label="Provider"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            fullWidth
          >
            {KNOWN_PROVIDERS.map((p) => (
              <MenuItem key={p.value} value={p.value}>
                {p.label}
              </MenuItem>
            ))}
          </TextField>

          {provider === "other" && (
            <TextField
              label="Provider name"
              value={customProvider}
              onChange={(e) => setCustomProvider(e.target.value)}
              placeholder="e.g. oracle-cloud, digitalocean, alibaba-cloud"
              required
              fullWidth
            />
          )}

          <TextField
            label="Account name"
            value={accountName}
            onChange={(e) => setAccountName(e.target.value)}
            helperText="A label to tell your accounts apart, e.g. 'Production AWS'"
            autoFocus
            required
            fullWidth
          />

          {regionSuggestions.length > 0 ? (
            <Autocomplete
              freeSolo
              options={regionSuggestions}
              getOptionLabel={(option) => (typeof option === "string" ? option : `${option.code} — ${option.label}`)}
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
                }
              }}
              onInputChange={(_, newInputValue, reason) => {
                if (reason === "input") setRegion(newInputValue);
              }}
              slotProps={{ listbox: { style: { maxHeight: 300, overflow: "auto" } } }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Region"
                  placeholder="Search by region code or location, e.g. eu-west-2 or London"
                  required
                  helperText={
                    matchedSuggestion ? `Timezone will be set to ${matchedSuggestion.timezone}` : undefined
                  }
                />
              )}
            />
          ) : (
            <TextField
              label="Region"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="e.g. us-east-1, eastus, us-central1"
              required
              fullWidth
            />
          )}

          <TextField
            label="Account / Subscription / Project ID (optional)"
            value={accountIdentifier}
            onChange={(e) => setAccountIdentifier(e.target.value)}
            fullWidth
          />

          <Typography variant="subtitle2">
            Credentials
            {isEdit && (
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                (leave blank to keep the existing stored credentials)
              </Typography>
            )}
          </Typography>
          {credentialFields.map((field, index) => (
            <Stack direction="row" spacing={1} key={index} alignItems="center">
              <TextField
                label="Key"
                placeholder="e.g. access_key_id"
                value={field.key}
                onChange={(e) => {
                  const next = [...credentialFields];
                  next[index] = { ...next[index], key: e.target.value };
                  setCredentialFields(next);
                }}
                size="small"
                fullWidth
              />
              <TextField
                label="Value"
                placeholder="e.g. secret_access_key value"
                type="password"
                value={field.value}
                onChange={(e) => {
                  const next = [...credentialFields];
                  next[index] = { ...next[index], value: e.target.value };
                  setCredentialFields(next);
                }}
                size="small"
                fullWidth
              />
              <IconButton
                size="small"
                aria-label="Remove field"
                disabled={credentialFields.length === 1}
                onClick={() => setCredentialFields(credentialFields.filter((_, i) => i !== index))}
              >
                <RemoveCircleOutlineIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}
          <Button
            size="small"
            startIcon={<AddIcon />}
            sx={{ alignSelf: "flex-start" }}
            onClick={() => setCredentialFields([...credentialFields, { key: "", value: "" }])}
          >
            Add credential field
          </Button>
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
