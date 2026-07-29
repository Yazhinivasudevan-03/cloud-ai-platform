import { useEffect, useState } from "react";
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
import UploadFileIcon from "@mui/icons-material/UploadFileOutlined";
import { ConnectionTestResultPanel } from "@/components/ConnectionTestResultPanel";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { KNOWN_PROVIDERS } from "@/utils/cloudProviders";
import {
  accountAliasLabel,
  hasStructuredCredentialFields,
  PROVIDER_CREDENTIAL_FIELDS,
} from "@/utils/cloudCredentialFields";
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
  // Structured, provider-specific credential fields (Phase 26) - used
  // instead of the generic key/value editor above for any provider with a
  // real backend adapter (see utils/cloudCredentialFields.ts).
  const [structuredCredentials, setStructuredCredentials] = useState<Record<string, string>>({});

  const resolvedProvider = provider === "other" ? customProvider.trim() : provider;
  const usesStructuredFields = hasStructuredCredentialFields(resolvedProvider);

  const testConnectionMutation = useMutation({
    mutationFn: () =>
      cloudProviderAccountsApi.testConnection({
        provider: resolvedProvider,
        region: region.trim(),
        credentials: structuredCredentials,
      }),
  });

  // Resets the Phase 26 credential-testing state whenever the dialog opens
  // (including reopening for a different account) or the provider changes -
  // stale field values/results from a previous provider must never leak in.
  useEffect(() => {
    if (open) {
      setStructuredCredentials({});
      testConnectionMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, account?.id]);

  useEffect(() => {
    setStructuredCredentials({});
    testConnectionMutation.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedProvider]);

  const requiredStructuredFieldsFilled =
    usesStructuredFields &&
    PROVIDER_CREDENTIAL_FIELDS[resolvedProvider]
      .filter((f) => f.required)
      .every((f) => (structuredCredentials[f.key] ?? "").trim() !== "") &&
    region.trim() !== "";

  // Searchable region suggestions (utils/cloudRegions.ts, the same central
  // catalog CloudAccountTimezoneFormDialog already uses) - a provider with
  // no curated table (a custom "Other" provider) falls back to today's
  // plain free-text Region field, unchanged.
  const regionSuggestions = regionSuggestionsFor(resolvedProvider);
  const matchedSuggestion = regionSuggestions.find((r) => r.code === region);

  const hasNewCredentials = usesStructuredFields
    ? Object.values(structuredCredentials).some((v) => v.trim() !== "")
    : credentialFields.some((f) => f.key.trim() !== "" && f.value.trim() !== "");

  const mutation = useMutation({
    mutationFn: () => {
      const credentials = usesStructuredFields
        ? Object.fromEntries(
            Object.entries(structuredCredentials).filter(([, value]) => value.trim() !== "")
          )
        : Object.fromEntries(
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

      // Phase 26, requirement 5: automatically begin monitoring once new
      // credentials are saved - re-validates them for real server-side
      // (never trusts the earlier Test Connection click) and, on success,
      // unblocks region sync/resource inventory/alerting for this account.
      // Best-effort: a validation failure here must not block the save
      // itself, which already succeeded - the account simply stays in its
      // "credentials not validated yet" state, surfaced on the Cloud
      // Account detail page and Dashboard.
      if (hasNewCredentials) {
        cloudProviderAccountsApi.validateCredentials(savedAccount.id).catch(() => {});
      }

      onClose();
    },
  });

  const canSubmit =
    accountName.trim() !== "" &&
    region.trim() !== "" &&
    resolvedProvider !== "" &&
    (isEdit || hasNewCredentials);

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
            label={accountAliasLabel(resolvedProvider)}
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

          {usesStructuredFields ? (
            <>
              {PROVIDER_CREDENTIAL_FIELDS[resolvedProvider].map((field) => (
                <TextField
                  key={field.key}
                  label={field.label}
                  placeholder={isEdit ? "Leave blank to keep the existing value" : field.placeholder}
                  helperText={field.helperText}
                  value={structuredCredentials[field.key] ?? ""}
                  onChange={(e) =>
                    setStructuredCredentials((prev) => ({ ...prev, [field.key]: e.target.value }))
                  }
                  type={field.type === "password" ? "password" : "text"}
                  multiline={field.type === "multiline"}
                  minRows={field.type === "multiline" ? 4 : undefined}
                  fullWidth
                />
              ))}
              {resolvedProvider === "gcp" && (
                <Button size="small" component="label" startIcon={<UploadFileIcon />} sx={{ alignSelf: "flex-start" }}>
                  Upload service account JSON file
                  <input
                    type="file"
                    accept="application/json"
                    hidden
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      const reader = new FileReader();
                      reader.onload = () =>
                        setStructuredCredentials((prev) => ({
                          ...prev,
                          service_account_json: String(reader.result ?? ""),
                        }));
                      reader.readAsText(file);
                    }}
                  />
                </Button>
              )}

              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Button
                  variant="outlined"
                  disabled={!requiredStructuredFieldsFilled}
                  loading={testConnectionMutation.isPending}
                  onClick={() => testConnectionMutation.mutate()}
                >
                  Test Connection
                </Button>
                <Typography variant="caption" color="text.secondary">
                  Validates these credentials with a real, live call before you save - nothing is stored
                  until you click {isEdit ? "Save" : "Add"}.
                </Typography>
              </Stack>
              <ErrorAlert error={testConnectionMutation.error} />
              {testConnectionMutation.data && <ConnectionTestResultPanel result={testConnectionMutation.data} />}
            </>
          ) : (
            <>
              {(provider === "ibm" || provider === "digitalocean") && (
                <Typography variant="caption" color="text.secondary">
                  Live connection testing isn't available for this provider yet - credentials are still
                  saved encrypted, but "Test Connection" can't verify them against a real API in this
                  pass.
                </Typography>
              )}
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
            </>
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
