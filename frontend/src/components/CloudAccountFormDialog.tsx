import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
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
import type { CloudProviderAccount } from "@/types";

interface CredentialField {
  key: string;
  value: string;
}

export function CloudAccountFormDialog({
  open,
  account,
  onClose,
}: {
  open: boolean;
  account: CloudProviderAccount | null;
  onClose: () => void;
}) {
  const isEdit = account !== null;
  const queryClient = useQueryClient();

  const [provider, setProvider] = useState(account?.provider ?? "aws");
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts"] });
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

          <TextField
            label="Region"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            placeholder="e.g. us-east-1, eastus, us-central1"
            required
            fullWidth
          />

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
