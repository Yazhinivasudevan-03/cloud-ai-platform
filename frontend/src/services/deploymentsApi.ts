import { httpClient } from "./httpClient";
import type { Deployment, DeploymentStatus, PaginatedResponse } from "@/types";

export interface DeploymentPayload {
  name: string;
  namespace?: string;
  image?: string | null;
  version?: string | null;
  replicas?: number;
  status?: DeploymentStatus;
  memory_limit_mb?: number | null;
}

export const deploymentsApi = {
  listForMicroservice: (
    microserviceId: number,
    page = 1,
    pageSize = 20,
    status?: string,
    namespace?: string,
  ) =>
    httpClient
      .get<PaginatedResponse<Deployment>>(`/microservices/${microserviceId}/deployments`, {
        params: { page, page_size: pageSize, status, namespace },
      })
      .then((r) => r.data),

  get: (deploymentId: number) =>
    httpClient.get<Deployment>(`/deployments/${deploymentId}`).then((r) => r.data),

  create: (microserviceId: number, payload: DeploymentPayload) =>
    httpClient
      .post<Deployment>(`/microservices/${microserviceId}/deployments`, payload)
      .then((r) => r.data),

  update: (deploymentId: number, payload: Partial<DeploymentPayload>) =>
    httpClient.put<Deployment>(`/deployments/${deploymentId}`, payload).then((r) => r.data),

  remove: (deploymentId: number) =>
    httpClient.delete(`/deployments/${deploymentId}`).then(() => undefined),
};
