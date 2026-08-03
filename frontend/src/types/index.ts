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

// A single Pydantic/FastAPI validation error entry (see the backend's
// RequestValidationError handler, app/middleware/error_handler.py) - the
// `error.details` array on a 422 response is a list of these.
export interface ApiValidationErrorDetail {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: ApiValidationErrorDetail[];
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
  phone_number: string | null;
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  country: string | null;
  email_verified: boolean;
  is_active: boolean;
  is_superuser: boolean;
  roles: Role[];
}

export interface UserProfileUpdate {
  full_name?: string | null;
  phone_number?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  company_name?: string | null;
  country?: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// --- Sign up / email verification / password reset (Phase 24) ----------

export interface RegisterPayload {
  first_name: string;
  last_name: string;
  email: string;
  mobile_number: string;
  company_name?: string;
  country: string;
  password: string;
  confirm_password: string;
}

// Identical to User, plus a one-time email-verification token/link - real
// SMTP delivery isn't wired up in this environment, so the raw token/link
// is returned here for the "check your email" screen to show directly.
export interface RegisterResponse extends User {
  verification_token: string;
  verification_link: string;
}

export interface MessageResponse {
  message: string;
}

export interface EmailVerificationResult {
  email_verified: boolean;
  message: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
  confirm_new_password: string;
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

// --- Project cost thresholds (Phase 21) ---------------------------------

export interface ProjectCostThreshold {
  project_id: number;
  monthly_budget: number | null;
  cost_warning_threshold: number | null;
  cost_critical_threshold: number | null;
  cost_saturated_threshold: number | null;
  effective_cost_warning_threshold: number;
  effective_cost_critical_threshold: number;
  effective_cost_saturated_threshold: number;
}

export interface ProjectCostThresholdUpdate {
  monthly_budget?: number | null;
  cost_warning_threshold?: number | null;
  cost_critical_threshold?: number | null;
  cost_saturated_threshold?: number | null;
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
  disk_limit_mb: number | null;
  network_limit_kbps: number | null;
  cloud_provider_account_id: number | null;
  cloud_resource_identifier: string | null;
  cloud_account_timezone_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface CloudSyncResult {
  deployment_id: number;
  cloud_provider_account_id: number;
  provider: string;
  resource_identifier: string;
  synced_at: string;
  resource_usage_id: number;
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
  // Phase 22 - multi-timezone support. Null unless this metric's deployment
  // is linked to a configured cloud account timezone entry.
  utc_timestamp: string | null;
  local_timestamp: string | null;
  deployment_timezone: string | null;
  region: string | null;
  provider: string | null;
  // Multi-tenant SaaS isolation - makes the owning cloud account/user
  // explicit on every response.
  cloud_provider_account_id: number | null;
  owner_user_id: number | null;
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
  project_id: number | null;
  alert_type: string;
  severity: AlertSeverity;
  threshold_percent: number | null;
  message: string;
  status: AlertStatus;
  triggered_at: string;
  resolved_at: string | null;
  created_at: string;
  // Phase 22 - multi-timezone support. Null unless this alert's deployment
  // is linked to a configured cloud account timezone entry.
  alert_time_utc: string | null;
  alert_time_local: string | null;
  deployment_timezone: string | null;
  region: string | null;
  provider: string | null;
  // Multi-tenant SaaS isolation - makes the owning cloud account/user
  // explicit on every response (null for a genuinely platform-wide
  // alert, visible only to a platform superuser).
  cloud_provider_account_id: number | null;
  owner_user_id: number | null;
}

export interface AlertEvaluationSummary {
  deployments_evaluated: number;
  projects_evaluated: number;
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
  // Phase 23 - alert context read through from the linked Alert; null for
  // a notification with no alert_id or an alert with no resolvable value.
  severity: AlertSeverity | null;
  alert_type: string | null;
  provider: string | null;
  region: string | null;
  resource: string | null;
  alert_time_utc: string | null;
  alert_time_local: string | null;
  // SMS delivery tracking - populated only for channel="sms" rows.
  cloud_provider_account_id: number | null;
  phone_number: string | null;
  message_sid: string | null;
  delivery_status: string | null;
}

export interface NotificationSummary {
  unread_total: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
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
  recommendations_auto_applied: number;
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
  // Phase 26: whether the stored credentials have actually been proven to
  // work via a real test_connection() call - drives the "Cloud credentials
  // are required before monitoring can begin" gating states.
  credentials_validated: boolean;
  credentials_validated_at: string | null;
}

export interface CloudAccountDeploymentSummary {
  deployment_id: number;
  deployment_name: string;
  namespace: string;
  cloud_resource_identifier: string;
  latest_usage: ResourceUsage | null;
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

// --- Cloud Credential Configuration workflow (Phase 26) ------------------

export interface TestConnectionRequest {
  provider: string;
  region: string;
  credentials: Record<string, string>;
}

export interface ConnectionTestResult {
  provider: string;
  account_id: string | null;
  account_alias: string | null;
  principal: string | null;
  region: string;
  status: string;
}

// --- Dynamic multi-cloud region discovery (Phase 25) --------------------

export const ALL_REGIONS_SENTINEL = "all";

export interface CloudRegion {
  id: string;
  display_name: string;
  // Phase 30: best-effort enrichment from the backend's central region
  // metadata table - null when that table doesn't cover this region yet
  // (never fabricated, the region itself is never hidden).
  country?: string | null;
  timezone?: string | null;
}

export interface CloudAccountRegions {
  selected_region: string;
  regions: CloudRegion[];
  last_region_sync: string | null;
  connection_status: string;
  // Phase 30 (automatic region -> IANA timezone mapping): null when
  // selected_region is "all" (no single timezone applies) or the region
  // isn't in the metadata table yet.
  selected_region_timezone?: string | null;
}

// --- Read-only cloud resource inventory (Phase 25C) ---------------------

export const RESOURCE_CATEGORIES = ["compute", "clusters", "databases", "storage", "networking"] as const;
export type ResourceCategory = (typeof RESOURCE_CATEGORIES)[number];

export interface CloudResource {
  id: string;
  name: string;
  type: string;
  region: string;
  status: string;
  created_at: string | null;
}

export interface CloudResourceList {
  category: string;
  region: string;
  items: CloudResource[];
}

export const PROVISIONABLE_RESOURCE_TYPES = ["compute", "storage", "networking"] as const;
export type ProvisionableResourceType = (typeof PROVISIONABLE_RESOURCE_TYPES)[number];

export interface DeployResourceRequest {
  resource_type: ProvisionableResourceType;
  region: string;
  spec: Record<string, string>;
}

export interface DestroyResourceRequest {
  region: string;
  confirm: string;
}

// --- Automatic AWS resource discovery (Phase 29) -------------------------
// Persisted, auto-refreshing counterpart to the on-demand CloudResource
// browse endpoint above - distinct type names so the two never get
// confused despite the overlapping domain.

export interface Ec2Metric {
  cpu_usage_percent: number;
  memory_usage_mb: number | null;
  network_in_kbps: number;
  network_out_kbps: number;
  disk_read_bytes: number;
  disk_write_bytes: number;
  status_check_failed: number | null;
  recorded_at: string;
}

export interface DiscoveredResource {
  id: number;
  resource_type: string;
  external_id: string;
  name: string;
  region: string;
  availability_zone: string | null;
  status: string;
  instance_type: string | null;
  public_ip: string | null;
  private_ip: string | null;
  is_active: boolean;
  first_seen_at: string;
  last_seen_at: string;
  latest_metric: Ec2Metric | null;
}

export interface DiscoveredResourceList {
  items: DiscoveredResource[];
}

export interface CloudAccountDiscoverySummary {
  total_instances: number;
  running_instances: number;
  stopped_instances: number;
  resource_counts_by_type: Record<string, number>;
  last_discovery_at: string | null;
  last_discovery_error: string | null;
}

// --- Notification settings (Phase 20) ----------------------------------

// The 5 tiered categories support per-tier (60/80/90%) checkboxes; the
// other 4 are simple on/off - see backend app/notifications/alert_preferences.py.
export const TIERED_ALERT_CATEGORIES = [
  "cpu", "memory", "disk", "network", "storage", "cloud_usage", "cloud_cost",
  "api_latency", "error_rate", "pod_restart", "security",
] as const;
export const SIMPLE_ALERT_CATEGORIES = [
  "node_failure", "container_failure", "ai_prediction", "resource_optimization",
] as const;
export type AlertCategory = (typeof TIERED_ALERT_CATEGORIES)[number] | (typeof SIMPLE_ALERT_CATEGORIES)[number];

export interface AlertCategoryPreference {
  enabled: boolean;
  warning: boolean;
  critical: boolean;
  saturated: boolean;
}

export interface NotificationSetting {
  email_enabled: boolean;
  sms_enabled: boolean;
  telegram_enabled: boolean;
  slack_enabled: boolean;
  teams_enabled: boolean;
  instant_alerts_enabled: boolean;
  daily_summary_enabled: boolean;
  alert_sound_enabled: boolean;
  dnd_start_time: string | null; // "HH:MM:SS"
  dnd_end_time: string | null;
  timezone: string;
  telegram_bot_token_configured: boolean;
  telegram_chat_id_configured: boolean;
  slack_webhook_configured: boolean;
  teams_webhook_configured: boolean;
  secondary_email: string | null;
  country_code: string | null;
  telegram_username: string | null;
  notification_language: string;
  alert_preferences: Record<AlertCategory, AlertCategoryPreference>;
}

export interface NotificationSettingUpdate {
  email_enabled?: boolean;
  sms_enabled?: boolean;
  telegram_enabled?: boolean;
  slack_enabled?: boolean;
  teams_enabled?: boolean;
  instant_alerts_enabled?: boolean;
  daily_summary_enabled?: boolean;
  alert_sound_enabled?: boolean;
  dnd_start_time?: string | null;
  dnd_end_time?: string | null;
  timezone?: string;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  slack_webhook_url?: string;
  teams_webhook_url?: string;
  secondary_email?: string;
  country_code?: string;
  telegram_username?: string;
  notification_language?: string;
  alert_preferences?: Partial<Record<AlertCategory, Partial<AlertCategoryPreference>>>;
}

// Real, distinct reasons a test notification wasn't sent (Phase 23 follow-up) -
// never a fabricated success; each only appears when the corresponding real
// condition/exception actually occurred (see backend email_notifier.py).
export type NotificationFailureReason =
  | "not_configured"
  | "no_recipient"
  | "auth_failed"
  | "unreachable"
  | "invalid_recipient"
  | "failed";

export interface NotificationSettingTestResult {
  email_sent: boolean | null;
  email_reason: NotificationFailureReason | "sent" | null;
  secondary_email_sent: boolean | null;
  secondary_email_reason: NotificationFailureReason | "sent" | null;
  sms_sent: boolean | null;
  sms_reason: NotificationFailureReason | "sent" | null;
  telegram_sent: boolean | null;
  telegram_reason: NotificationFailureReason | "sent" | null;
  slack_sent: boolean | null;
  slack_reason: NotificationFailureReason | "sent" | null;
}

// --- Cloud account alert thresholds (Phase 20-21) -----------------------

export interface CloudAccountAlertThreshold {
  cloud_provider_account_id: number;
  cpu_warning_threshold: number | null;
  cpu_critical_threshold: number | null;
  cpu_saturated_threshold: number | null;
  memory_warning_threshold: number | null;
  memory_critical_threshold: number | null;
  memory_saturated_threshold: number | null;
  disk_warning_threshold: number | null;
  disk_critical_threshold: number | null;
  disk_saturated_threshold: number | null;
  network_warning_threshold: number | null;
  network_critical_threshold: number | null;
  network_saturated_threshold: number | null;
  effective_cpu_warning_threshold: number;
  effective_cpu_critical_threshold: number;
  effective_cpu_saturated_threshold: number;
  effective_memory_warning_threshold: number;
  effective_memory_critical_threshold: number;
  effective_memory_saturated_threshold: number;
  effective_disk_warning_threshold: number;
  effective_disk_critical_threshold: number;
  effective_disk_saturated_threshold: number;
  effective_network_warning_threshold: number;
  effective_network_critical_threshold: number;
  effective_network_saturated_threshold: number;
}

export interface CloudAccountAlertThresholdUpdate {
  cpu_warning_threshold?: number | null;
  cpu_critical_threshold?: number | null;
  cpu_saturated_threshold?: number | null;
  memory_warning_threshold?: number | null;
  memory_critical_threshold?: number | null;
  memory_saturated_threshold?: number | null;
  disk_warning_threshold?: number | null;
  disk_critical_threshold?: number | null;
  disk_saturated_threshold?: number | null;
  network_warning_threshold?: number | null;
  network_critical_threshold?: number | null;
  network_saturated_threshold?: number | null;
}

// --- Cloud account deployment timezones (Phase 22) ------------------------

export interface CloudAccountTimezone {
  id: number;
  cloud_provider_account_id: number;
  provider: string;
  region: string;
  availability_zone: string | null;
  label: string;
  timezone: string;
  utc_offset: string;
  current_local_time: string;
  created_at: string;
  updated_at: string;
}

export interface CloudAccountTimezoneCreate {
  region: string;
  availability_zone?: string | null;
  label: string;
  timezone: string;
}

export interface CloudAccountTimezoneUpdate {
  region?: string;
  availability_zone?: string | null;
  label?: string;
  timezone?: string;
}

export interface TimezoneValidationResult {
  timezone: string;
  valid: boolean;
  utc_offset: string | null;
  current_local_time: string | null;
  error: string | null;
}
