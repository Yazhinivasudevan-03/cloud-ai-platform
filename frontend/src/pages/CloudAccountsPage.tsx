import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Link,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/EditOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime, formatMegabytes, formatPercent } from "@/utils/formatters";
import type { CloudProviderAccount } from "@/types";

// A recognized subset for a nicer label - the backend accepts any provider
// string at all (see CloudProviderAccountCreate.provider), so "Other" plus
// a free-text field is how any provider not in this list is supported,
// satisfying "any cloud provider" without hardcoding an exhaustive list.
const KNOWN_PROVIDERS = [
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
  { value: "gcp", label: "GCP" },
  { value: "other", label: "Other" },
];

function providerLabel(provider: string): string {
  const known = KNOWN_PROVIDERS.find((p) => p.value === provider);
  return known ? known.label : provider;
}

export function CloudAccountsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [formOpen, setFormOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<CloudProviderAccount | null>(null);
  const [accountToDelete, setAccountToDelete] = useState<CloudProviderAccount | null>(null);
  const [usageAccount, setUsageAccount] = useState<CloudProviderAccount | null>(null);

  const accountsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", page, pageSize],
    queryFn: () => cloudProviderAccountsApi.list({ page, pageSize }),
  });

  const deleteMutation = useMutation({
    mutationFn: (accountId: number) => cloudProviderAccountsApi.remove(accountId),
    onSuccess: () => {
      setAccountToDelete(null);
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts"] });
    },
  });

  const columns: DataTableColumn<CloudProviderAccount>[] = [
    {
      header: "Account",
      render: (a) => (
        <Typography variant="body2" fontWeight={600}>
          {a.account_name}
        </Typography>
      ),
    },
    { header: "Provider", render: (a) => <Chip size="small" label={providerLabel(a.provider)} /> },
    { header: "Region", render: (a) => a.region },
    { header: "Identifier", render: (a) => a.account_identifier || "-" },
    {
      header: "Status",
      render: (a) => (
        <Chip
          size="small"
          label={a.is_active ? "Active" : "Inactive"}
          color={a.is_active ? "success" : "default"}
          variant="outlined"
        />
      ),
    },
    { header: "Added", render: (a) => formatDateTime(a.created_at) },
    {
      header: "",
      align: "right",
      render: (a) => (
        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
          <IconButton size="small" aria-label="View usage" onClick={() => setUsageAccount(a)}>
            <MonitorHeartOutlinedIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            aria-label="Edit cloud account"
            onClick={() => {
              setEditingAccount(a);
              setFormOpen(true);
            }}
          >
            <EditIcon fontSize="small" />
          </IconButton>
          <IconButton size="small" aria-label="Delete cloud account" onClick={() => setAccountToDelete(a)}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Cloud Accounts"
        subtitle="Configure your own cloud provider accounts - any provider, any region, no limit on how many you add."
        actions={
          <Button
            startIcon={<AddIcon />}
            variant="contained"
            onClick={() => {
              setEditingAccount(null);
              setFormOpen(true);
            }}
          >
            Add cloud account
          </Button>
        }
      />
      <ErrorAlert error={accountsQuery.error} />
      <DataTable
        columns={columns}
        rows={accountsQuery.data?.items ?? []}
        total={accountsQuery.data?.meta.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        isLoading={accountsQuery.isLoading}
        emptyMessage="No cloud accounts configured yet. Add one to get started."
      />

      <CloudAccountFormDialog
        open={formOpen}
        account={editingAccount}
        onClose={() => {
          setFormOpen(false);
          setEditingAccount(null);
        }}
      />

      <ConfirmDialog
        open={accountToDelete !== null}
        title="Delete cloud account"
        description={`Delete "${accountToDelete?.account_name}"? This cannot be undone.`}
        confirmLabel="Delete"
        destructive
        onCancel={() => setAccountToDelete(null)}
        onConfirm={() => accountToDelete && deleteMutation.mutate(accountToDelete.id)}
      />

      <AccountUsageDialog account={usageAccount} onClose={() => setUsageAccount(null)} />
    </>
  );
}

function AccountUsageDialog({
  account,
  onClose,
}: {
  account: CloudProviderAccount | null;
  onClose: () => void;
}) {
  const usageQuery = useQuery({
    queryKey: ["cloud-provider-accounts", account?.id, "deployments"],
    queryFn: () => cloudProviderAccountsApi.listLinkedDeployments(account!.id),
    enabled: account !== null,
  });

  return (
    <Dialog open={account !== null} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>
        Live usage - {account?.account_name}
        <Typography variant="body2" color="text.secondary">
          Every deployment linked to this account, with its most recently synced metrics.
        </Typography>
      </DialogTitle>
      <DialogContent>
        <ErrorAlert error={usageQuery.error} />
        {usageQuery.isLoading && <Typography variant="body2">Loading...</Typography>}
        {usageQuery.data && usageQuery.data.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
            No deployments are linked to this account yet. Link one from a deployment's "Cloud Sync"
            tab.
          </Typography>
        )}
        {usageQuery.data && usageQuery.data.length > 0 && (
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {usageQuery.data.map((d) => (
              <Paper key={d.deployment_id} variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap">
                  <Box>
                    <Link
                      component={RouterLink}
                      to={`/deployments/${d.deployment_id}`}
                      variant="body1"
                      fontWeight={600}
                      underline="hover"
                    >
                      {d.deployment_name}
                    </Link>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {d.namespace} - {d.cloud_resource_identifier}
                    </Typography>
                  </Box>
                  {d.latest_usage ? (
                    <Stack direction="row" spacing={1}>
                      <Chip size="small" label={`CPU ${formatPercent(d.latest_usage.cpu_usage_percent, 1)}`} />
                      <Chip size="small" label={`Mem ${formatMegabytes(d.latest_usage.memory_usage_mb)}`} />
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`Net ${d.latest_usage.network_in_kbps.toFixed(1)}/${d.latest_usage.network_out_kbps.toFixed(1)} kbps`}
                      />
                    </Stack>
                  ) : (
                    <Chip size="small" variant="outlined" label="Never synced yet" />
                  )}
                </Stack>
                {d.latest_usage && (
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                    Last synced {formatDateTime(d.latest_usage.recorded_at)}
                  </Typography>
                )}
              </Paper>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

interface CredentialField {
  key: string;
  value: string;
}

function CloudAccountFormDialog({
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
