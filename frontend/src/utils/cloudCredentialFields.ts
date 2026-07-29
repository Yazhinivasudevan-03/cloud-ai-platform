// Phase 26: the Cloud Credential Configuration workflow's per-provider
// structured credential fields - one small, explicit config per provider
// that already has a real backend CloudProviderClient adapter (see
// backend/app/integrations/providers/), so "Test Connection" performs a
// genuine, live validation call rather than a fabricated success. IBM
// Cloud/DigitalOcean/"Other" have no backend adapter at all yet (still
// UI-only "connect" since Phase 24) and fall back to the existing generic
// key/value credential editor, with an honest note that live validation
// isn't available for them yet - never a fake "Test Connection" that
// doesn't actually call anything real.
export interface CredentialFieldConfig {
  key: string;
  label: string;
  type: "text" | "password" | "multiline";
  required: boolean;
  helperText?: string;
  placeholder?: string;
}

export const PROVIDER_CREDENTIAL_FIELDS: Record<string, CredentialFieldConfig[]> = {
  aws: [
    { key: "access_key_id", label: "AWS Access Key ID", type: "text", required: true },
    { key: "secret_access_key", label: "AWS Secret Access Key", type: "password", required: true },
    { key: "session_token", label: "AWS Session Token (optional)", type: "password", required: false },
  ],
  azure: [
    { key: "subscription_id", label: "Subscription ID", type: "text", required: true },
    { key: "tenant_id", label: "Tenant ID", type: "text", required: true },
    { key: "client_id", label: "Client ID", type: "text", required: true },
    { key: "client_secret", label: "Client Secret", type: "password", required: true },
  ],
  gcp: [
    {
      key: "service_account_json",
      label: "Service Account JSON",
      type: "multiline",
      required: true,
      helperText: "Paste the full service account key JSON (or upload the file below)",
    },
    {
      key: "project_id",
      label: "Project ID (optional)",
      type: "text",
      required: false,
      helperText: "Only needed if it isn't already present in the service account JSON",
    },
  ],
  oci: [
    { key: "user", label: "User OCID", type: "text", required: true },
    { key: "tenancy", label: "Tenancy OCID", type: "text", required: true },
    { key: "fingerprint", label: "Key Fingerprint", type: "text", required: true },
    { key: "key_content", label: "Private Key (PEM)", type: "multiline", required: true },
    { key: "compartment_id", label: "Compartment OCID (optional)", type: "text", required: false },
  ],
  alibaba: [
    { key: "access_key_id", label: "AccessKey ID", type: "text", required: true },
    { key: "access_key_secret", label: "AccessKey Secret", type: "password", required: true },
  ],
};

// Providers with a real backend adapter capable of a genuine Test
// Connection call (see app/integrations/provider_factory.py's registry) -
// every other provider value falls back to the generic key/value editor
// with live validation disabled/disclosed rather than faked.
export const PROVIDERS_WITH_LIVE_VALIDATION = new Set(Object.keys(PROVIDER_CREDENTIAL_FIELDS));

export function hasStructuredCredentialFields(provider: string): boolean {
  return provider in PROVIDER_CREDENTIAL_FIELDS;
}

const ACCOUNT_ALIAS_LABELS: Record<string, string> = {
  aws: "Account Alias (optional)",
  azure: "Subscription Alias (optional)",
  gcp: "Project Alias (optional)",
  oci: "Tenancy Alias (optional)",
  alibaba: "Account Alias (optional)",
};

export function accountAliasLabel(provider: string): string {
  return ACCOUNT_ALIAS_LABELS[provider] ?? "Account / Subscription / Project ID (optional)";
}
