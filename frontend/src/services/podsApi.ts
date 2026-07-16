import { httpClient } from "./httpClient";
import type { PaginatedResponse, Pod, PodStatus } from "@/types";

export interface PodPayload {
  pod_name: string;
  node_name?: string | null;
  ip_address?: string | null;
  status?: PodStatus;
  restart_count?: number;
}

export const podsApi = {
  listForDeployment: (deploymentId: number, page = 1, pageSize = 20, status?: string) =>
    httpClient
      .get<PaginatedResponse<Pod>>(`/deployments/${deploymentId}/pods`, {
        params: { page, page_size: pageSize, status },
      })
      .then((r) => r.data),

  create: (deploymentId: number, payload: PodPayload) =>
    httpClient.post<Pod>(`/deployments/${deploymentId}/pods`, payload).then((r) => r.data),

  update: (podId: number, payload: Partial<PodPayload>) =>
    httpClient.put<Pod>(`/pods/${podId}`, payload).then((r) => r.data),

  remove: (podId: number) => httpClient.delete(`/pods/${podId}`).then(() => undefined),
};
