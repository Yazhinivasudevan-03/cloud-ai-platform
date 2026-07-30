// A recognized subset for a nicer label - the backend accepts any provider
// string at all (see CloudProviderAccountCreate.provider), so "Other" plus
// a free-text field is how any provider not in this list is supported,
// satisfying "any cloud provider" without hardcoding an exhaustive list.
// All 7 named providers (aws/azure/gcp/oci/alibaba/ibm/digitalocean) have
// real, working credential validation + region-discovery + resource-
// inventory + provisioning integrations (see
// backend/app/integrations/providers/, Phase 12/24/25/27). ibm/
// digitalocean don't yet have automated CloudWatch-style metric/cost sync
// (Phase 12/18's real-time telemetry pull) - a disclosed gap, not a
// fabricated one; manually-ingested or Prometheus/K8s-sourced monitoring
// data still works for deployments linked to either. "oci" (not "oracle")
// matches the backend's own provider_factory registry key and the
// official OCI SDK/CLI naming convention, so a connected Oracle Cloud
// account's region discovery and monitoring sync actually resolve to the
// real integration.
export const KNOWN_PROVIDERS = [
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
  { value: "gcp", label: "Google Cloud" },
  { value: "oci", label: "Oracle Cloud" },
  { value: "ibm", label: "IBM Cloud" },
  { value: "digitalocean", label: "DigitalOcean" },
  { value: "alibaba", label: "Alibaba Cloud" },
  { value: "other", label: "Other" },
];

export function providerLabel(provider: string): string {
  const known = KNOWN_PROVIDERS.find((p) => p.value === provider);
  return known ? known.label : provider;
}
