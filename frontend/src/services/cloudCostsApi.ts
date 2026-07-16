import { httpClient } from "./httpClient";
import type { CloudCost, CostForecast, PaginatedResponse } from "@/types";

export interface CloudCostPayload {
  provider: string;
  service_name: string;
  cost_amount: number;
  currency?: string;
  billing_period_start: string;
  billing_period_end: string;
}

export const cloudCostsApi = {
  listForProject: (projectId: number, page = 1, pageSize = 20) =>
    httpClient
      .get<PaginatedResponse<CloudCost>>(`/projects/${projectId}/cloud-costs`, {
        params: { page, page_size: pageSize },
      })
      .then((r) => r.data),

  ingest: (projectId: number, payload: CloudCostPayload) =>
    httpClient.post<CloudCost>(`/projects/${projectId}/cloud-costs`, payload).then((r) => r.data),

  forecast: (projectId: number) =>
    httpClient.get<CostForecast>(`/projects/${projectId}/cost-forecast`).then((r) => r.data),
};
