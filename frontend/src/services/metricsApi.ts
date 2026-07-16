import { httpClient } from "./httpClient";
import type { Metric, PaginatedResponse, ResourceUsage } from "@/types";

export interface ResourceUsagePayload {
  cpu_usage_percent: number;
  memory_usage_mb: number;
  disk_usage_mb: number;
  network_in_kbps: number;
  network_out_kbps: number;
  recorded_at: string;
}

export interface MetricPayload {
  metric_type: string;
  value: number;
  unit: string;
  recorded_at: string;
  pod_id?: number | null;
}

export const metricsApi = {
  listResourceUsage: (deploymentId: number, page = 1, pageSize = 50, since?: string, until?: string) =>
    httpClient
      .get<PaginatedResponse<ResourceUsage>>(`/deployments/${deploymentId}/resource-usage`, {
        params: { page, page_size: pageSize, since, until },
      })
      .then((r) => r.data),

  ingestResourceUsage: (deploymentId: number, payload: ResourceUsagePayload) =>
    httpClient
      .post<ResourceUsage>(`/deployments/${deploymentId}/resource-usage`, payload)
      .then((r) => r.data),

  listMetrics: (deploymentId: number, page = 1, pageSize = 50, metricType?: string) =>
    httpClient
      .get<PaginatedResponse<Metric>>(`/deployments/${deploymentId}/metrics`, {
        params: { page, page_size: pageSize, metric_type: metricType },
      })
      .then((r) => r.data),

  ingestMetric: (deploymentId: number, payload: MetricPayload) =>
    httpClient.post<Metric>(`/deployments/${deploymentId}/metrics`, payload).then((r) => r.data),
};
