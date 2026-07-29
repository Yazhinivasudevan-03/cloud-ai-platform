import { Alert, Stack, Typography } from "@mui/material";
import type { ConnectionTestResult } from "@/types";

const FIELD_LABELS: Record<string, string> = {
  aws: "AWS Account ID",
  azure: "Subscription ID",
  gcp: "Project ID",
  oci: "Tenancy OCID",
  alibaba: "Account ID",
};

// Phase 26: the Cloud Credential Configuration workflow's "✅ Connection
// Successful" panel - shown after a real Test Connection call succeeds,
// displaying exactly what that live call actually returned (never a
// fabricated placeholder; account_alias/principal are honestly null when
// the provider has no cheap way to supply one - see _identity() in
// backend/app/integrations/cloud_provider_client.py).
export function ConnectionTestResultPanel({ result }: { result: ConnectionTestResult }) {
  return (
    <Alert severity="success" icon={false}>
      <Typography variant="subtitle2" gutterBottom>
        Connection Successful
      </Typography>
      <Stack spacing={0.5}>
        <Typography variant="body2">
          {FIELD_LABELS[result.provider] ?? "Account ID"}: <strong>{result.account_id ?? "Not available"}</strong>
        </Typography>
        <Typography variant="body2">
          Account Alias: <strong>{result.account_alias ?? "Not available"}</strong>
        </Typography>
        <Typography variant="body2">
          IAM User / Role / Principal: <strong>{result.principal ?? "Not available"}</strong>
        </Typography>
        <Typography variant="body2">
          Default Region: <strong>{result.region}</strong>
        </Typography>
        <Typography variant="body2">
          Connection Status: <strong>{result.status}</strong>
        </Typography>
      </Stack>
    </Alert>
  );
}
