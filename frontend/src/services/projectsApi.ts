import { httpClient } from "./httpClient";
import type { PaginatedResponse, Project } from "@/types";

export interface ProjectPayload {
  name: string;
  description?: string | null;
}

export interface ListProjectsParams {
  name?: string;
  sortBy?: "name" | "created_at";
  order?: "asc" | "desc";
  page?: number;
  pageSize?: number;
}

export const projectsApi = {
  list: (params: ListProjectsParams = {}) =>
    httpClient
      .get<PaginatedResponse<Project>>("/projects", {
        params: {
          name: params.name || undefined,
          sort_by: params.sortBy,
          order: params.order,
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
        },
      })
      .then((r) => r.data),

  get: (projectId: number) => httpClient.get<Project>(`/projects/${projectId}`).then((r) => r.data),

  create: (payload: ProjectPayload) =>
    httpClient.post<Project>("/projects", payload).then((r) => r.data),

  update: (projectId: number, payload: Partial<ProjectPayload>) =>
    httpClient.put<Project>(`/projects/${projectId}`, payload).then((r) => r.data),

  remove: (projectId: number) => httpClient.delete(`/projects/${projectId}`).then(() => undefined),
};
