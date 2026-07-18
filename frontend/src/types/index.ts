/**
 * Shared TypeScript types mirroring the backend's Pydantic schemas
 * (backend/app/schemas/*.py). Kept centralized rather than scattered across
 * per-resource service files, since almost every page needs several of
 * these together (e.g. a Deployment page needs Deployment, ResourceUsage,
 * Prediction, Alert, and OptimizationRecommendation all at once).
 */

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  meta: PaginationMeta;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

// --- Auth / Users -----------------------------------------------------

export interface Role {
  id: number;
  name: string;
  description: string | null;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  roles: Role[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type RoleName = "viewer" | "operator" | "admin";

// --- Domain hierarchy ---------------------------------------------------

export interface Project {
  id: number;
  name: string;
  description: string | null;
  owner_id: number;
  created_at: string;
  updated_at: string;
}

export interface Microservice {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  repository_url: string | null;
  language: string | null;
  created_at: string;
  updated_at: string;
}

export type DeploymentStatus = "running" | "pending" | "failed" | "unknown";

export interface Deployment {
  id: number;
  microservice_id: number;
  name: string;
  namespace: string;
  image: string | null;
  version: string | null;
  replicas: number;
  status: DeploymentStatus;
  memory_limit_mb: number | null;
  created_at: string;
  updated_at: string;
}

export type PodStatus = "running" | "pending" | "failed" | "succeeded" | "unknown";

export interface Pod {
  id: number;
  deployment_id: number;
  pod_name: string;
  node_name: string | null;
  ip_address: string | null;
  status: PodStatus;
  restart_count: number;
  created_at: string;
  updated_at: string;
}

// --- Metrics / resource usage -------------------------------------------

export interface Metric {
  id: number;
  deployment_id: number | null;
  pod_id: number | null;
  metric_type: string;
  value: number;
  unit: string;
  recorded_at: string;
  created_at: string;
}

export interface ResourceUsage {
  id: number;
  deployment_id: number;
  cpu_usage_percent: number;
  memory_usage_mb: number;
  disk_usage_mb: number;
  network_in_kbps: number;
  network_out_kbps: number;
  recorded_at: string;
  created_at: string;
}

// --- AI output (read-only) ----------------------------------------------

export interface Prediction {
  id: number;
  deployment_id: number;
  model_type: string;
  metric_type: string;
  predicted_value: number;
  confidence_score: number;
  target_timestamp: string;
  generated_at: string;
  created_at: string;
}

export interface AnomalyDetection {
  id: number;
  deployment_id: number;
  metric_type: string;
  anomaly_score: number;
  is_anomaly: boolean;
  detected_at: string;
  details: string | null;
  created_at: string;
}

export interface FailurePrediction {
  id: number;
  deployment_id: number;
  pod_id: number | null;
  failure_type: string;
  probability: number;
  predicted_at: string;
  created_at: string;
}

// --- Alerts / notifications ----------------------------------------------

export type AlertSeverity = "warning" | "critical";
export type AlertStatus = "active" | "acknowledged" | "resolved";

export interface Alert {
  id: number;
  deployment_id: number | null;
  alert_type: string;
  severity: AlertSeverity;
  threshold_percent: number | null;
  message: string;
  status: AlertStatus;
  triggered_at: string;
  resolved_at: string | null;
  created_at: string;
}

export interface AlertEvaluationSummary {
  deployments_evaluated: number;
  alerts_created: number;
  alerts_resolved: number;
  notifications_sent: number;
}

export interface Notification {
  id: number;
  user_id: number;
  alert_id: number | null;
  channel: string;
  message: string;
  is_read: boolean;
  sent_at: string | null;
  created_at: string;
}

// --- Optimization / cost -------------------------------------------------

export type OptimizationRecommendationStatus = "pending" | "applied" | "dismissed";

export interface OptimizationRecommendation {
  id: number;
  deployment_id: number;
  recommendation_type: string;
  description: string;
  estimated_savings: number | null;
  status: OptimizationRecommendationStatus;
  created_at: string;
  updated_at: string;
}

export interface OptimizationEvaluationSummary {
  deployments_evaluated: number;
  recommendations_created: number;
  recommendations_dismissed: number;
}

export interface CloudCost {
  id: number;
  project_id: number;
  provider: string;
  service_name: string;
  cost_amount: number;
  currency: string;
  billing_period_start: string;
  billing_period_end: string;
  created_at: string;
}

export interface CostForecast {
  predicted_next_month_cost: number;
  currency: string;
  method: "linear_regression" | "naive_last_period";
  historical_periods_used: number;
  trend_slope_per_month: number | null;
}

// --- Cloud provider accounts (self-service, unlimited count) -----------

// A common, recognized subset for icon/label purposes in the UI - the
// backend itself accepts any provider string at all, so "other" (or any
// value not in this list) must still be handled gracefully client-side.
export type KnownCloudProvider = "aws" | "azure" | "gcp";

export interface CloudProviderAccount {
  id: number;
  user_id: number;
  provider: string;
  account_name: string;
  region: string;
  account_identifier: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CloudProviderAccountCreate {
  provider: string;
  account_name: string;
  region: string;
  account_identifier?: string;
  credentials: Record<string, string>;
}

export interface CloudProviderAccountUpdate {
  provider?: string;
  account_name?: string;
  region?: string;
  account_identifier?: string;
  credentials?: Record<string, string>;
  is_active?: boolean;
}
