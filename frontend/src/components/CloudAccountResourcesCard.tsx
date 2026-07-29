import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CircularProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatusChip } from "@/components/StatusChip";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime } from "@/utils/formatters";
import { ALL_REGIONS_SENTINEL, RESOURCE_CATEGORIES, type ResourceCategory } from "@/types";

const CATEGORY_LABELS: Record<ResourceCategory, string> = {
  compute: "Compute",
  clusters: "Clusters",
  databases: "Databases",
  storage: "Storage",
  networking: "Networking",
};

export function CloudAccountResourcesCard({ accountId }: { accountId: number }) {
  const [category, setCategory] = useState<ResourceCategory>("compute");

  const regionsQuery = useQuery({
    queryKey: ["cloud-provider-accounts", accountId, "regions"],
    queryFn: () => cloudProviderAccountsApi.getRegions(accountId),
  });
  const [region, setRegion] = useState<string | null>(null);
  const effectiveRegion = region ?? regionsQuery.data?.selected_region ?? ALL_REGIONS_SENTINEL;

  const resourcesQuery = useQuery({
    queryKey: ["cloud-provider-accounts", accountId, "resources", category, effectiveRegion],
    queryFn: () => cloudProviderAccountsApi.listResources(accountId, category, effectiveRegion),
    enabled: !!regionsQuery.data,
  });

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" spacing={1} sx={{ mb: 1 }}>
        <Typography variant="h6">Resources</Typography>
        <TextField
          select
          size="small"
          label="Region"
          value={effectiveRegion}
          onChange={(e) => setRegion(e.target.value)}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value={ALL_REGIONS_SENTINEL}>All Regions (aggregate)</MenuItem>
          {(regionsQuery.data?.regions ?? []).map((r) => (
            <MenuItem key={r.id} value={r.id}>
              {r.display_name}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <Tabs
        value={category}
        onChange={(_, value: ResourceCategory) => setCategory(value)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
      >
        {RESOURCE_CATEGORIES.map((c) => (
          <Tab key={c} value={c} label={CATEGORY_LABELS[c]} />
        ))}
      </Tabs>

      <ErrorAlert error={regionsQuery.error ?? resourcesQuery.error} />

      {resourcesQuery.isLoading && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 3 }}>
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Loading {CATEGORY_LABELS[category].toLowerCase()}...
          </Typography>
        </Stack>
      )}

      {resourcesQuery.data && resourcesQuery.data.items.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
          No {CATEGORY_LABELS[category].toLowerCase()} found for this account
          {effectiveRegion === ALL_REGIONS_SENTINEL ? " in any discovered region." : ` in ${effectiveRegion}.`}
        </Typography>
      )}

      {resourcesQuery.data && resourcesQuery.data.items.length > 0 && (
        <TableContainer sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Region</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {resourcesQuery.data.items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.name}</TableCell>
                  <TableCell>{item.type}</TableCell>
                  <TableCell>{item.region}</TableCell>
                  <TableCell>
                    <StatusChip value={item.status} />
                  </TableCell>
                  <TableCell>{item.created_at ? formatDateTime(item.created_at) : "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Paper>
  );
}
