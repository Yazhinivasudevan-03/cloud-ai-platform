import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Chip,
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
  TextField,
  Typography,
} from "@mui/material";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import DnsOutlinedIcon from "@mui/icons-material/DnsOutlined";
import PauseCircleOutlinedIcon from "@mui/icons-material/PauseCircleOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import { ErrorAlert } from "@/components/ErrorAlert";
import { StatCard } from "@/components/StatCard";
import { StatusChip } from "@/components/StatusChip";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import { formatDateTime, formatRelativeTime } from "@/utils/formatters";

const RESOURCE_TYPE_LABELS: Record<string, string> = {
  ec2_instance: "EC2 Instances",
  ecs_cluster: "ECS Clusters",
  eks_cluster: "EKS Clusters",
  lambda_function: "Lambda Functions",
  rds_database: "RDS Databases",
  s3_bucket: "S3 Buckets",
  ebs_volume: "EBS Volumes",
  load_balancer: "Load Balancers",
  auto_scaling_group: "Auto Scaling Groups",
  vpc: "VPCs",
  subnet: "Subnets",
  security_group: "Security Groups",
  cloudwatch_alarm: "CloudWatch Alarms",
};
const RESOURCE_TYPES = Object.keys(RESOURCE_TYPE_LABELS);

export function CloudAccountDiscoveredResourcesCard({ accountId }: { accountId: number }) {
  const queryClient = useQueryClient();
  const [resourceType, setResourceType] = useState("ec2_instance");

  const summaryQuery = useQuery({
    queryKey: ["cloud-provider-accounts", accountId, "discovered-resources", "summary"],
    queryFn: () => cloudProviderAccountsApi.getDiscoverySummary(accountId),
    refetchInterval: 30_000,
  });
  const resourcesQuery = useQuery({
    queryKey: ["cloud-provider-accounts", accountId, "discovered-resources", resourceType],
    queryFn: () => cloudProviderAccountsApi.listDiscoveredResources(accountId, resourceType),
    refetchInterval: 30_000,
  });

  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<unknown>(null);

  const handleDiscoverNow = async () => {
    setDiscovering(true);
    setDiscoverError(null);
    try {
      await cloudProviderAccountsApi.discoverResources(accountId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "discovered-resources"] }),
      ]);
    } catch (err) {
      setDiscoverError(err);
    } finally {
      setDiscovering(false);
    }
  };

  const isEc2 = resourceType === "ec2_instance";
  const items = resourcesQuery.data?.items ?? [];

  return (
    <Paper sx={{ p: 2.5 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" spacing={1} sx={{ mb: 2 }}>
        <Typography variant="h6">Discovered AWS Resources</Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={discovering ? <CircularProgress size={14} /> : <RefreshIcon />}
          disabled={discovering}
          onClick={handleDiscoverNow}
        >
          Discover Now
        </Button>
      </Stack>

      <ErrorAlert error={discoverError} />

      {summaryQuery.data?.last_discovery_error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Last discovery run reported an error: {summaryQuery.data.last_discovery_error}
        </Alert>
      )}

      <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: "wrap" }}>
        <StatCard label="EC2 instances" value={summaryQuery.data?.total_instances ?? "-"} icon={DnsOutlinedIcon} />
        <StatCard
          label="Running"
          value={summaryQuery.data?.running_instances ?? "-"}
          icon={CheckCircleOutlinedIcon}
          color="success.main"
        />
        <StatCard
          label="Stopped"
          value={summaryQuery.data?.stopped_instances ?? "-"}
          icon={PauseCircleOutlinedIcon}
          color="text.secondary"
        />
      </Stack>

      {summaryQuery.data?.last_discovery_at && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
          Last discovered {formatRelativeTime(summaryQuery.data.last_discovery_at)}
        </Typography>
      )}

      <TextField
        select
        size="small"
        label="Resource type"
        value={resourceType}
        onChange={(e) => setResourceType(e.target.value)}
        sx={{ minWidth: 220, mb: 2 }}
      >
        {RESOURCE_TYPES.map((t) => (
          <MenuItem key={t} value={t}>
            {RESOURCE_TYPE_LABELS[t]}
          </MenuItem>
        ))}
      </TextField>

      <ErrorAlert error={resourcesQuery.error} />

      {resourcesQuery.isLoading && (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 3 }}>
          <CircularProgress size={18} />
          <Typography variant="body2" color="text.secondary">
            Loading {RESOURCE_TYPE_LABELS[resourceType].toLowerCase()}...
          </Typography>
        </Stack>
      )}

      {resourcesQuery.data && items.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
          No {RESOURCE_TYPE_LABELS[resourceType].toLowerCase()} discovered for this account yet.
        </Typography>
      )}

      {items.length > 0 && (
        <TableContainer sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>ID</TableCell>
                {isEc2 && <TableCell>Type</TableCell>}
                <TableCell>Region</TableCell>
                {isEc2 && <TableCell>AZ</TableCell>}
                {isEc2 && <TableCell>Public IP</TableCell>}
                {isEc2 && <TableCell>Private IP</TableCell>}
                <TableCell>State</TableCell>
                {isEc2 && <TableCell>CPU</TableCell>}
                {isEc2 && <TableCell>Memory</TableCell>}
                {isEc2 && <TableCell>Network In/Out</TableCell>}
                <TableCell>Last seen</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{item.name}</TableCell>
                  <TableCell>
                    <Typography variant="body2" fontFamily="monospace">
                      {item.external_id}
                    </Typography>
                  </TableCell>
                  {isEc2 && <TableCell>{item.instance_type ?? "-"}</TableCell>}
                  <TableCell>{item.region}</TableCell>
                  {isEc2 && <TableCell>{item.availability_zone ?? "-"}</TableCell>}
                  {isEc2 && <TableCell>{item.public_ip ?? "-"}</TableCell>}
                  {isEc2 && <TableCell>{item.private_ip ?? "-"}</TableCell>}
                  <TableCell>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      <StatusChip value={item.status} />
                      {!item.is_active && <Chip size="small" label="Terminated" color="default" />}
                    </Stack>
                  </TableCell>
                  {isEc2 && (
                    <TableCell>
                      {item.latest_metric ? `${item.latest_metric.cpu_usage_percent.toFixed(1)}%` : "-"}
                    </TableCell>
                  )}
                  {isEc2 && (
                    <TableCell>
                      {item.latest_metric?.memory_usage_mb != null
                        ? `${item.latest_metric.memory_usage_mb.toFixed(0)} MB`
                        : "N/A"}
                    </TableCell>
                  )}
                  {isEc2 && (
                    <TableCell>
                      {item.latest_metric
                        ? `${item.latest_metric.network_in_kbps.toFixed(1)} / ${item.latest_metric.network_out_kbps.toFixed(1)} kbps`
                        : "-"}
                    </TableCell>
                  )}
                  <TableCell>{formatDateTime(item.last_seen_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Paper>
  );
}
