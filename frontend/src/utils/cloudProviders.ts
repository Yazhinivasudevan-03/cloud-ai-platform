// A recognized subset for a nicer label - the backend accepts any provider
// string at all (see CloudProviderAccountCreate.provider), so "Other" plus
// a free-text field is how any provider not in this list is supported,
// satisfying "any cloud provider" without hardcoding an exhaustive list.
// aws/azure/gcp/oci/alibaba have real, working cloud-sync + region-discovery
// integrations (see backend/app/integrations/providers/, Phase 12/24/25);
// ibm/digitalocean can still be connected and monitored (manually-ingested
// or Prometheus/K8s-sourced data), just without automated cloud-vendor-API
// metric/cost sync yet. "oci" (not "oracle") matches the backend's own
// provider_factory registry key and the official OCI SDK/CLI naming
// convention, so a connected Oracle Cloud account's region discovery and
// monitoring sync actually resolve to the real integration.
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
