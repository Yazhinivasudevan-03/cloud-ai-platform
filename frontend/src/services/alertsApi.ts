import { httpClient } from "./httpClient";
import type { Alert, AlertEvaluationSummary, AlertStatus, PaginatedResponse } from "@/types";

export const alertsApi = {
  listGlobal: (
    page = 1,
    pageSize = 20,
    status?: string,
    severity?: string,
    deploymentId?: number,
  ) =>
    httpClient
      .get<PaginatedResponse<Alert>>("/alerts", {
        params: { page, page_size: pageSize, status, severity, deployment_id: deploymentId },
      })
      .then((r) => r.data),

  listForDeployment: (deploymentId: number, page = 1, pageSize = 20, status?: string) =>
    httpClient
      .get<PaginatedResponse<Alert>>(`/deployments/${deploymentId}/alerts`, {
        params: { page, page_size: pageSize, status },
      })
      .then((r) => r.data),

  updateStatus: (alertId: number, status: AlertStatus) =>
    httpClient.patch<Alert>(`/alerts/${alertId}`, { status }).then((r) => r.data),

  evaluateNow: () =>
    httpClient.post<AlertEvaluationSummary>("/alerts/evaluate").then((r) => r.data),
};
