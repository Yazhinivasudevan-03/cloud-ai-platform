/** All dashboard data-fetching in one place, reused by both the popup (full
 * fetch on open) and the background service worker (lightweight alert-only
 * poll). Every call here is an existing backend endpoint - see docs/PHASE_32.md
 * for the full request -> endpoint mapping; nothing here invents new backend
 * behavior. */
import { apiGet } from "./api-client";
import type {
  AlertRead,
  CloudAccountDeploymentSummary,
  CloudCostRead,
  CloudProviderAccountRead,
  NotificationSummary,
  OptimizationRecommendationRead,
  PaginatedResponse,
  ProjectRead,
} from "./types";

export interface ActiveAlertsSnapshot {
  alerts: AlertRead[];
  criticalCount: number;
  warningCount: number;
}

/** Cheap enough to call every background alarm tick: one request. */
export async function fetchActiveAlerts(): Promise<ActiveAlertsSnapshot> {
  const page = await apiGet<PaginatedResponse<AlertRead>>("/alerts", {
    status: "active",
    page: 1,
    page_size: 100,
  });
  const alerts = page.items;
  return {
    alerts,
    criticalCount: alerts.filter((a) => a.severity === "critical").length,
    warningCount: alerts.filter((a) => a.severity === "warning").length,
  };
}

export interface AccountWithUsage {
  account: CloudProviderAccountRead;
  deployments: CloudAccountDeploymentSummary[];
}

export interface FullDashboardSnapshot {
  accounts: AccountWithUsage[];
  activeAlerts: ActiveAlertsSnapshot;
  recommendations: OptimizationRecommendationRead[];
  monthCostByCurrency: Record<string, number>;
  notificationSummary: NotificationSummary;
}

function firstOfMonthIso(): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
}

/** The full fan-out - only run when the popup is actually open, not on every
 * background tick, to keep background API load proportionate (per the
 * approved plan). */
export async function fetchFullDashboard(): Promise<FullDashboardSnapshot> {
  const [accountsPage, activeAlerts, recommendationsPage, notificationSummary, projectsPage] = await Promise.all([
    apiGet<PaginatedResponse<CloudProviderAccountRead>>("/cloud-provider-accounts", { page: 1, page_size: 50 }),
    fetchActiveAlerts(),
    apiGet<PaginatedResponse<OptimizationRecommendationRead>>("/optimization-recommendations", {
      status: "pending",
      page: 1,
      page_size: 20,
    }),
    apiGet<NotificationSummary>("/notifications/summary"),
    apiGet<PaginatedResponse<ProjectRead>>("/projects", { page: 1, page_size: 50 }),
  ]);

  const accounts: AccountWithUsage[] = await Promise.all(
    accountsPage.items.map(async (account) => ({
      account,
      deployments: await apiGet<CloudAccountDeploymentSummary[]>(
        `/cloud-provider-accounts/${account.id}/deployments`,
      ),
    })),
  );

  const since = firstOfMonthIso();
  const monthCostByCurrency: Record<string, number> = {};
  await Promise.all(
    projectsPage.items.map(async (project) => {
      const costsPage = await apiGet<PaginatedResponse<CloudCostRead>>(`/projects/${project.id}/cloud-costs`, {
        since,
        page: 1,
        page_size: 100,
      });
      for (const cost of costsPage.items) {
        monthCostByCurrency[cost.currency] = (monthCostByCurrency[cost.currency] ?? 0) + cost.cost_amount;
      }
    }),
  );

  return {
    accounts,
    activeAlerts,
    recommendations: recommendationsPage.items,
    monthCostByCurrency,
    notificationSummary,
  };
}
