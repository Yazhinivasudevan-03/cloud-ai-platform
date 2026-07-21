import { Link as RouterLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Link,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime, formatMegabytes, formatPercent } from "@/utils/formatters";
import type { CloudProviderAccount } from "@/types";

export function AccountUsageDialog({
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
