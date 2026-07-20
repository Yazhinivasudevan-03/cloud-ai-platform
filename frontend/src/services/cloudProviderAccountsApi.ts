import { httpClient } from "./httpClient";
import type {
  CloudAccountDeploymentSummary,
  CloudProviderAccount,
  CloudProviderAccountCreate,
  CloudProviderAccountUpdate,
  PaginatedResponse,
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

  listLinkedDeployments: (accountId: number) =>
    httpClient
      .get<CloudAccountDeploymentSummary[]>(`/cloud-provider-accounts/${accountId}/deployments`)
      .then((r) => r.data),
};
