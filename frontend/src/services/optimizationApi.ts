import { httpClient } from "./httpClient";
import type {
  OptimizationEvaluationSummary,
  OptimizationRecommendation,
  OptimizationRecommendationStatus,
  PaginatedResponse,
} from "@/types";

export const optimizationApi = {
  listGlobal: (
    page = 1,
    pageSize = 20,
    status?: string,
    recommendationType?: string,
    deploymentId?: number,
  ) =>
    httpClient
      .get<PaginatedResponse<OptimizationRecommendation>>("/optimization-recommendations", {
        params: {
          page,
          page_size: pageSize,
          status,
          recommendation_type: recommendationType,
          deployment_id: deploymentId,
        },
      })
      .then((r) => r.data),

  listForDeployment: (deploymentId: number, page = 1, pageSize = 20, status?: string) =>
    httpClient
      .get<PaginatedResponse<OptimizationRecommendation>>(
        `/deployments/${deploymentId}/optimization-recommendations`,
        { params: { page, page_size: pageSize, status } },
      )
      .then((r) => r.data),

  updateStatus: (recommendationId: number, status: OptimizationRecommendationStatus) =>
    httpClient
      .patch<OptimizationRecommendation>(`/optimization-recommendations/${recommendationId}`, {
        status,
      })
      .then((r) => r.data),

  evaluateNow: () =>
    httpClient.post<OptimizationEvaluationSummary>("/optimization/evaluate").then((r) => r.data),
};
