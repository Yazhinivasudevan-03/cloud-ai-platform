import { httpClient } from "./httpClient";
import type { Microservice, PaginatedResponse } from "@/types";

export interface MicroservicePayload {
  name: string;
  description?: string | null;
  repository_url?: string | null;
  language?: string | null;
}

export const microservicesApi = {
  listForProject: (projectId: number, page = 1, pageSize = 20, name?: string) =>
    httpClient
      .get<PaginatedResponse<Microservice>>(`/projects/${projectId}/microservices`, {
        params: { page, page_size: pageSize, name: name || undefined },
      })
      .then((r) => r.data),

  get: (microserviceId: number) =>
    httpClient.get<Microservice>(`/microservices/${microserviceId}`).then((r) => r.data),

  create: (projectId: number, payload: MicroservicePayload) =>
    httpClient
      .post<Microservice>(`/projects/${projectId}/microservices`, payload)
      .then((r) => r.data),

  update: (microserviceId: number, payload: Partial<MicroservicePayload>) =>
    httpClient.put<Microservice>(`/microservices/${microserviceId}`, payload).then((r) => r.data),

  remove: (microserviceId: number) =>
    httpClient.delete(`/microservices/${microserviceId}`).then(() => undefined),
};
