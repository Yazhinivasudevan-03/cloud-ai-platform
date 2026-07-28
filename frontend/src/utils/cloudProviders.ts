// A recognized subset for a nicer label - the backend accepts any provider
// string at all (see CloudProviderAccountCreate.provider), so "Other" plus
// a free-text field is how any provider not in this list is supported,
// satisfying "any cloud provider" without hardcoding an exhaustive list.
// aws/azure/gcp have real, working cloud-sync integrations (see
// backend/app/integrations/); oracle/ibm/digitalocean/alibaba can still be
// connected and monitored (manually-ingested or Prometheus/K8s-sourced
// data), just without automated cloud-vendor-API metric/cost sync yet.
export const KNOWN_PROVIDERS = [
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
  { value: "gcp", label: "Google Cloud" },
  { value: "oracle", label: "Oracle Cloud" },
  { value: "ibm", label: "IBM Cloud" },
  { value: "digitalocean", label: "DigitalOcean" },
  { value: "alibaba", label: "Alibaba Cloud" },
  { value: "other", label: "Other" },
];

export function providerLabel(provider: string): string {
  const known = KNOWN_PROVIDERS.find((p) => p.value === provider);
  return known ? known.label : provider;
}
