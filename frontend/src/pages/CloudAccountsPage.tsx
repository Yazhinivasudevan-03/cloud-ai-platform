import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Chip, IconButton, Stack, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/EditOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorAlert } from "@/components/ErrorAlert";
import { CloudAccountFormDialog } from "@/components/CloudAccountFormDialog";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime } from "@/utils/formatters";
import { providerLabel } from "@/utils/cloudProviders";
import type { CloudProviderAccount } from "@/types";

export function CloudAccountsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [formOpen, setFormOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState<CloudProviderAccount | null>(null);
  const [accountToDelete, setAccountToDelete] = useState<CloudProviderAccount | null>(null);

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
          <IconButton
            size="small"
            aria-label="Monitor cloud account"
            onClick={() => navigate(`/cloud-accounts/${a.id}`)}
          >
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
    </>
  );
}
