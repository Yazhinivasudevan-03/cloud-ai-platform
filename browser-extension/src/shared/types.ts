/** Mirrors of the exact backend response shapes this extension consumes.
 * Only the fields actually used are declared - see the plan doc
 * (docs/PHASE_32.md) for which backend schema each one maps to. */

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserRead {
  id: number;
  username: string;
  email: string;
}

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

export interface CloudProviderAccountRead {
  id: number;
  user_id: number;
  provider: string;
  account_name: string;
  region: string;
  account_identifier: string | null;
  is_active: boolean;
  credentials_validated: boolean;
  credentials_validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResourceUsageRead {
  id: number;
  deployment_id: number;
  cpu_usage_percent: number;
  memory_usage_mb: number;
  disk_usage_mb: number;
  network_in_kbps: number;
  network_out_kbps: number;
  recorded_at: string;
}

export interface CloudAccountDeploymentSummary {
  deployment_id: number;
  deployment_name: string;
  namespace: string;
  cloud_resource_identifier: string;
  latest_usage: ResourceUsageRead | null;
}

export type AlertSeverity = "warning" | "critical";
export type AlertStatus = "active" | "acknowledged" | "resolved";

export interface AlertRead {
  id: number;
  deployment_id: number | null;
  project_id: number | null;
  alert_type: string;
  severity: AlertSeverity;
  threshold_percent: number | null;
  message: string;
  status: AlertStatus;
  triggered_at: string;
  resolved_at: string | null;
}

export interface OptimizationRecommendationRead {
  id: number;
  deployment_id: number;
  recommendation_type: string;
  description: string;
  estimated_savings: number | null;
  status: string;
  created_at: string;
}

export interface ProjectRead {
  id: number;
  name: string;
  owner_id: number;
}

export interface CloudCostRead {
  id: number;
  project_id: number;
  provider: string;
  service_name: string;
  cost_amount: number;
  currency: string;
  billing_period_start: string;
  billing_period_end: string;
}

export interface NotificationSummary {
  unread_total: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
}

export interface ExtensionSettings {
  notificationsEnabled: boolean;
  notificationSound: boolean;
  /** Minutes between background alarm ticks. Clamped to >= 1 - chrome.alarms
   * refuses periods below one minute, a real MV3 platform limit. */
  refreshIntervalMinutes: number;
  theme: "dark" | "light" | "system";
  backendBaseUrl: string;
  webAppBaseUrl: string;
}

export const DEFAULT_SETTINGS: ExtensionSettings = {
  notificationsEnabled: true,
  notificationSound: true,
  refreshIntervalMinutes: 2,
  theme: "system",
  backendBaseUrl: "http://localhost:8000/api/v1",
  webAppBaseUrl: "http://localhost:3000",
};
