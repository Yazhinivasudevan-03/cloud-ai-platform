// A recognized subset for a nicer label - the backend accepts any provider
// string at all (see CloudProviderAccountCreate.provider), so "Other" plus
// a free-text field is how any provider not in this list is supported,
// satisfying "any cloud provider" without hardcoding an exhaustive list.
export const KNOWN_PROVIDERS = [
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
  { value: "gcp", label: "GCP" },
  { value: "other", label: "Other" },
];

export function providerLabel(provider: string): string {
  const known = KNOWN_PROVIDERS.find((p) => p.value === provider);
  return known ? known.label : provider;
}
