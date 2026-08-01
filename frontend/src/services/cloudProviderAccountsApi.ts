import { httpClient } from "./httpClient";
import type {
  Alert,
  CloudAccountAlertThreshold,
  CloudAccountAlertThresholdUpdate,
  CloudAccountDeploymentSummary,
  CloudAccountDiscoverySummary,
  CloudAccountRegions,
  CloudAccountTimezone,
  CloudAccountTimezoneCreate,
  CloudAccountTimezoneUpdate,
  CloudProviderAccount,
  CloudProviderAccountCreate,
  CloudProviderAccountUpdate,
  CloudResource,
  CloudResourceList,
  ConnectionTestResult,
  DeployResourceRequest,
  DestroyResourceRequest,
  DiscoveredResourceList,
  PaginatedResponse,
  ResourceCategory,
  TestConnectionRequest,
} from "@/types";

export interface ListCloudProviderAccountsParams {
  provider?: string;
  page?: number;
  pageSize?: number;
}

export const cloudProviderAccountsApi = {
  list: (params: ListCloudProviderAccountsParams = {}) =>
    httpClient
      .get<PaginatedResponse<CloudProviderAccount>>("/cloud-provider-accounts", {
        params: {
          provider: params.provider || undefined,
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
        },
      })
      .then((r) => r.data),

  get: (accountId: number) =>
    httpClient.get<CloudProviderAccount>(`/cloud-provider-accounts/${accountId}`).then((r) => r.data),

  create: (payload: CloudProviderAccountCreate) =>
    httpClient.post<CloudProviderAccount>("/cloud-provider-accounts", payload).then((r) => r.data),

  update: (accountId: number, payload: CloudProviderAccountUpdate) =>
    httpClient
      .put<CloudProviderAccount>(`/cloud-provider-accounts/${accountId}`, payload)
      .then((r) => r.data),

  remove: (accountId: number) =>
    httpClient.delete(`/cloud-provider-accounts/${accountId}`).then(() => undefined),

  testConnection: (payload: TestConnectionRequest) =>
    httpClient
      .post<ConnectionTestResult>("/cloud-provider-accounts/test-connection", payload)
      .then((r) => r.data),

  validateCredentials: (accountId: number) =>
    httpClient
      .post<ConnectionTestResult>(`/cloud-provider-accounts/${accountId}/validate-credentials`)
      .then((r) => r.data),

  listLinkedDeployments: (accountId: number) =>
    httpClient
      .get<CloudAccountDeploymentSummary[]>(`/cloud-provider-accounts/${accountId}/deployments`)
      .then((r) => r.data),

  listActiveAlerts: (accountId: number) =>
    httpClient.get<Alert[]>(`/cloud-provider-accounts/${accountId}/alerts`).then((r) => r.data),

  getAlertThresholds: (accountId: number) =>
    httpClient
      .get<CloudAccountAlertThreshold>(`/cloud-provider-accounts/${accountId}/alert-thresholds`)
      .then((r) => r.data),

  updateAlertThresholds: (accountId: number, payload: CloudAccountAlertThresholdUpdate) =>
    httpClient
      .put<CloudAccountAlertThreshold>(`/cloud-provider-accounts/${accountId}/alert-thresholds`, payload)
      .then((r) => r.data),

  listTimezones: (accountId: number) =>
    httpClient
      .get<CloudAccountTimezone[]>(`/cloud-provider-accounts/${accountId}/timezones`)
      .then((r) => r.data),

  createTimezone: (accountId: number, payload: CloudAccountTimezoneCreate) =>
    httpClient
      .post<CloudAccountTimezone>(`/cloud-provider-accounts/${accountId}/timezones`, payload)
      .then((r) => r.data),

  updateTimezone: (accountId: number, timezoneId: number, payload: CloudAccountTimezoneUpdate) =>
    httpClient
      .put<CloudAccountTimezone>(`/cloud-provider-accounts/${accountId}/timezones/${timezoneId}`, payload)
      .then((r) => r.data),

  deleteTimezone: (accountId: number, timezoneId: number) =>
    httpClient.delete(`/cloud-provider-accounts/${accountId}/timezones/${timezoneId}`).then(() => undefined),

  getRegions: (accountId: number) =>
    httpClient.get<CloudAccountRegions>(`/cloud-provider-accounts/${accountId}/regions`).then((r) => r.data),

  refreshRegions: (accountId: number) =>
    httpClient
      .post<CloudAccountRegions>(`/cloud-provider-accounts/${accountId}/refresh-regions`)
      .then((r) => r.data),

  selectRegion: (accountId: number, selectedRegion: string) =>
    httpClient
      .patch<CloudProviderAccount>(`/cloud-provider-accounts/${accountId}/region`, {
        selected_region: selectedRegion,
      })
      .then((r) => r.data),

  listResources: (accountId: number, category: ResourceCategory, region: string) =>
    httpClient
      .get<CloudResourceList>(`/cloud-provider-accounts/${accountId}/resources`, {
        params: { category, region },
      })
      .then((r) => r.data),

  deployResource: (accountId: number, payload: DeployResourceRequest) =>
    httpClient
      .post<CloudResource>(`/cloud-provider-accounts/${accountId}/resources/deploy`, payload)
      .then((r) => r.data),

  destroyResource: (
    accountId: number,
    resourceType: ResourceCategory,
    resourceId: string,
    payload: DestroyResourceRequest,
  ) =>
    httpClient
      .delete(`/cloud-provider-accounts/${accountId}/resources/${resourceType}/${encodeURIComponent(resourceId)}`, {
        data: payload,
      })
      .then(() => undefined),

  // --- Automatic AWS resource discovery (Phase 29) ---
  listDiscoveredResources: (accountId: number, resourceType?: string, activeOnly = true) =>
    httpClient
      .get<DiscoveredResourceList>(`/cloud-provider-accounts/${accountId}/discovered-resources`, {
        params: { resource_type: resourceType || undefined, active_only: activeOnly },
      })
      .then((r) => r.data),

  getDiscoverySummary: (accountId: number) =>
    httpClient
      .get<CloudAccountDiscoverySummary>(`/cloud-provider-accounts/${accountId}/discovered-resources/summary`)
      .then((r) => r.data),

  discoverResources: (accountId: number) =>
    httpClient
      .post<CloudAccountDiscoverySummary>(`/cloud-provider-accounts/${accountId}/discover-resources`)
      .then((r) => r.data),
};
