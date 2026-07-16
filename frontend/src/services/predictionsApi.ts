import { httpClient } from "./httpClient";
import type { AnomalyDetection, FailurePrediction, PaginatedResponse, Prediction } from "@/types";

export const predictionsApi = {
  listPredictions: (deploymentId: number, page = 1, pageSize = 50, metricType?: string) =>
    httpClient
      .get<PaginatedResponse<Prediction>>(`/deployments/${deploymentId}/predictions`, {
        params: { page, page_size: pageSize, metric_type: metricType },
      })
      .then((r) => r.data),

  listAnomalyDetections: (deploymentId: number, page = 1, pageSize = 50, isAnomaly?: boolean) =>
    httpClient
      .get<PaginatedResponse<AnomalyDetection>>(`/deployments/${deploymentId}/anomaly-detections`, {
        params: { page, page_size: pageSize, is_anomaly: isAnomaly },
      })
      .then((r) => r.data),

  listFailurePredictions: (deploymentId: number, page = 1, pageSize = 50) =>
    httpClient
      .get<PaginatedResponse<FailurePrediction>>(`/deployments/${deploymentId}/failure-predictions`, {
        params: { page, page_size: pageSize },
      })
      .then((r) => r.data),
};
