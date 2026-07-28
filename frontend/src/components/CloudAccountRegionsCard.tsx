import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime } from "@/utils/formatters";
import { ALL_REGIONS_SENTINEL } from "@/types";

const STATUS_COLOR: Record<string, "success" | "error" | "warning" | "default"> = {
  CONNECTED: "success",
  ERROR: "error",
  CREDENTIALS_EXPIRED: "warning",
};

export function CloudAccountRegionsCard({ accountId }: { accountId: number }) {
  const queryClient = useQueryClient();
  const regionsQueryKey = ["cloud-provider-accounts", accountId, "regions"];

  const regionsQuery = useQuery({
    queryKey: regionsQueryKey,
    queryFn: () => cloudProviderAccountsApi.getRegions(accountId),
  });

  const refreshMutation = useMutation({
    mutationFn: () => cloudProviderAccountsApi.refreshRegions(accountId),
    onSuccess: (data) => {
      queryClient.setQueryData(regionsQueryKey, data);
    },
  });

  // Switching regions invalidates every query this account's selected
  // region feeds into (deployments/alerts/dashboard already filter by
  // cloud_provider_account_id - Phase 24), so the whole page reloads with
  // data for the newly selected region instead of showing stale results.
  const selectMutation = useMutation({
    mutationFn: (selectedRegion: string) => cloudProviderAccountsApi.selectRegion(accountId, selectedRegion),
    onSuccess: (account) => {
      queryClient.setQueryData(regionsQueryKey, (prev: typeof regionsQuery.data) =>
        prev ? { ...prev, selected_region: account.region } : prev
      );
      queryClient.setQueryData(["cloud-provider-accounts", accountId], account);
      void queryClient.invalidateQueries({ queryKey: ["deployments"] });
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "deployments"] });
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "alerts"] });
    },
  });

  const data = regionsQuery.data;
  const isSwitching = selectMutation.isPending;
  const isRefreshing = refreshMutation.isPending;

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" sx={{ mb: 1 }}>
        <Typography variant="h6">Region</Typography>
        {data && (
          <Chip
            size="small"
            label={data.connection_status === "CONNECTED" ? "Connected" : data.connection_status}
            color={STATUS_COLOR[data.connection_status] ?? "default"}
            variant="outlined"
          />
        )}
      </Stack>

      <ErrorAlert error={regionsQuery.error ?? refreshMutation.error ?? selectMutation.error} />

      {regionsQuery.isLoading && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 2 }}>
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Fetching regions...
          </Typography>
        </Stack>
      )}

      {data && (
        <>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" sx={{ mt: 1 }}>
            <TextField
              select
              label="Region"
              size="small"
              value={data.selected_region}
              disabled={isSwitching || isRefreshing}
              onChange={(e) => selectMutation.mutate(e.target.value)}
              sx={{ minWidth: 260 }}
            >
              <MenuItem value={ALL_REGIONS_SENTINEL}>All Regions (aggregate)</MenuItem>
              {data.regions.map((region) => (
                <MenuItem key={region.id} value={region.id}>
                  {region.display_name}
                  {region.id !== region.display_name ? ` (${region.id})` : ""}
                </MenuItem>
              ))}
            </TextField>

            <Button
              size="small"
              startIcon={<RefreshIcon />}
              loading={isRefreshing}
              disabled={isSwitching}
              onClick={() => refreshMutation.mutate()}
            >
              Refresh Regions
            </Button>

            {isSwitching && (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={16} />
                <Typography variant="caption" color="text.secondary">
                  Changing region...
                </Typography>
              </Stack>
            )}
          </Stack>

          {data.regions.length === 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              No regions discovered yet for this account.
            </Typography>
          )}

          <Typography variant="caption" color="text.secondary" sx={{ mt: 1.5, display: "block" }}>
            {data.last_region_sync
              ? `Last synced ${formatDateTime(data.last_region_sync)}`
              : "Not synced yet"}
          </Typography>

          {refreshMutation.isSuccess && (
            <Typography variant="caption" color="success.main" sx={{ mt: 0.5, display: "block" }}>
              Regions refreshed.
            </Typography>
          )}
        </>
      )}
    </Paper>
  );
}
