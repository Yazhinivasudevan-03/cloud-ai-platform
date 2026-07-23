import { Link as RouterLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Box, Chip, Link, Paper, Stack, Typography } from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { CloudAccountAlertThresholdsCard } from "@/components/CloudAccountAlertThresholdsCard";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusChip } from "@/components/StatusChip";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime, formatMegabytes, formatPercent } from "@/utils/formatters";
import { providerLabel } from "@/utils/cloudProviders";
import type { Alert } from "@/types";

export function CloudAccountDetailPage() {
  const { accountId } = useParams();
  const id = Number(accountId);

  const accountQuery = useQuery({
    queryKey: ["cloud-provider-accounts", id],
    queryFn: () => cloudProviderAccountsApi.get(id),
  });
  const deploymentsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", id, "deployments"],
    queryFn: () => cloudProviderAccountsApi.listLinkedDeployments(id),
  });
  const alertsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", id, "alerts"],
    queryFn: () => cloudProviderAccountsApi.listActiveAlerts(id),
  });

  const alertColumns: DataTableColumn<Alert>[] = [
    { header: "Triggered at", render: (a) => formatDateTime(a.triggered_at) },
    { header: "Deployment", render: (a) => (a.deployment_id ? `#${a.deployment_id}` : "-") },
    { header: "Type", render: (a) => a.alert_type },
    { header: "Severity", render: (a) => <StatusChip value={a.severity} /> },
    { header: "Message", render: (a) => a.message },
  ];

  return (
    <>
      <PageHeader
        title={accountQuery.data?.account_name ?? "Cloud account"}
        subtitle={
          accountQuery.data
            ? `${providerLabel(accountQuery.data.provider)} - ${accountQuery.data.region}${
                accountQuery.data.account_identifier ? ` - ${accountQuery.data.account_identifier}` : ""
              }`
            : undefined
        }
        actions={
          accountQuery.data && (
            <Chip
              size="small"
              label={accountQuery.data.is_active ? "Active" : "Inactive"}
              color={accountQuery.data.is_active ? "success" : "default"}
              variant="outlined"
            />
          )
        }
      />
      <ErrorAlert error={accountQuery.error} />

      <Paper sx={{ p: 2.5, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Linked deployments
        </Typography>
        <ErrorAlert error={deploymentsQuery.error} />
        {deploymentsQuery.data && deploymentsQuery.data.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            No deployments are linked to this account yet. Link one from a deployment's "Cloud Sync"
            tab.
          </Typography>
        )}
        {deploymentsQuery.data && deploymentsQuery.data.length > 0 && (
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {deploymentsQuery.data.map((d) => (
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
      </Paper>

      <Box sx={{ mb: 3 }}>
        <CloudAccountAlertThresholdsCard accountId={id} />
      </Box>

      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" gutterBottom>
          Active alerts for this account
        </Typography>
        <ErrorAlert error={alertsQuery.error} />
        <DataTable
          columns={alertColumns}
          rows={alertsQuery.data ?? []}
          total={alertsQuery.data?.length ?? 0}
          page={1}
          pageSize={alertsQuery.data?.length || 20}
          onPageChange={() => {}}
          onPageSizeChange={() => {}}
          isLoading={alertsQuery.isLoading}
          emptyMessage="No active alerts for this account's deployments."
        />
      </Paper>
    </>
  );
}
