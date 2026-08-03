import { fetchFullDashboard } from "../../shared/dashboard-data";
import type { FullDashboardSnapshot } from "../../shared/dashboard-data";
import { formatCurrency, formatKbps, formatMb, formatPercent, formatRelativeTime } from "../../shared/format";
import { getLastSyncAt, getSettings, setLastSyncAt } from "../../shared/storage";
import type { CloudProviderAccountRead, ResourceUsageRead } from "../../shared/types";

interface DashboardCallbacks {
  onOpenSettings: () => void;
  onLogout: () => void;
}

function healthBadge(account: CloudProviderAccountRead): string {
  if (!account.is_active) return `<span class="badge neutral">Inactive</span>`;
  if (account.credentials_validated) return `<span class="badge success">Connected</span>`;
  return `<span class="badge warning">Needs attention</span>`;
}

function averageUsage(deployments: { latest_usage: ResourceUsageRead | null }[]): ResourceUsageRead | null {
  const withUsage = deployments.map((d) => d.latest_usage).filter((u): u is ResourceUsageRead => u !== null);
  if (withUsage.length === 0) return null;
  const sum = withUsage.reduce(
    (acc, u) => ({
      cpu_usage_percent: acc.cpu_usage_percent + u.cpu_usage_percent,
      memory_usage_mb: acc.memory_usage_mb + u.memory_usage_mb,
      disk_usage_mb: acc.disk_usage_mb + u.disk_usage_mb,
      network_in_kbps: acc.network_in_kbps + u.network_in_kbps,
      network_out_kbps: acc.network_out_kbps + u.network_out_kbps,
    }),
    { cpu_usage_percent: 0, memory_usage_mb: 0, disk_usage_mb: 0, network_in_kbps: 0, network_out_kbps: 0 },
  );
  const n = withUsage.length;
  return {
    id: 0,
    deployment_id: 0,
    cpu_usage_percent: sum.cpu_usage_percent / n,
    memory_usage_mb: sum.memory_usage_mb / n,
    disk_usage_mb: sum.disk_usage_mb / n,
    network_in_kbps: sum.network_in_kbps / n,
    network_out_kbps: sum.network_out_kbps / n,
    recorded_at: new Date().toISOString(),
  };
}

function openWebApp(path: string): void {
  void getSettings().then((settings) => chrome.tabs.create({ url: `${settings.webAppBaseUrl}${path}` }));
}

function renderSkeleton(container: HTMLElement, callbacks: DashboardCallbacks): void {
  container.innerHTML = `
    <div class="topbar">
      <h1>Cloud AI Platform Monitor</h1>
      <button class="icon-btn" id="settings-btn" title="Settings">⚙</button>
    </div>
    <div class="content">
      <div class="spinner">Loading your dashboard...</div>
    </div>
  `;
  container.querySelector<HTMLButtonElement>("#settings-btn")!.addEventListener("click", callbacks.onOpenSettings);
}

export async function renderDashboard(container: HTMLElement, callbacks: DashboardCallbacks): Promise<void> {
  renderSkeleton(container, callbacks);

  let snapshot: FullDashboardSnapshot;
  try {
    snapshot = await fetchFullDashboard();
    await setLastSyncAt(new Date().toISOString());
  } catch (err) {
    const content = container.querySelector<HTMLDivElement>(".content")!;
    const message = err instanceof Error ? err.message : "Failed to load dashboard.";
    content.innerHTML = `<div class="error">${message}</div>
      <button class="action" id="retry-btn" style="margin-top:8px">Retry</button>`;
    content.querySelector<HTMLButtonElement>("#retry-btn")!.addEventListener("click", () => {
      void renderDashboard(container, callbacks);
    });
    if (err instanceof Error && err.message.includes("log in")) callbacks.onLogout();
    return;
  }

  const lastSync = await getLastSyncAt();
  const avgUsage = averageUsage(snapshot.accounts.flatMap((a) => a.deployments));
  const costEntries = Object.entries(snapshot.monthCostByCurrency);

  const accountsHtml =
    snapshot.accounts.length === 0
      ? `<div class="empty">No cloud accounts connected yet.</div>`
      : snapshot.accounts
          .map(
            ({ account }) => `
        <div class="account-row">
          <div>
            <div class="account-name">${account.account_name}</div>
            <div class="account-meta">${account.provider.toUpperCase()} &middot; ${account.region}</div>
          </div>
          ${healthBadge(account)}
        </div>`,
          )
          .join("");

  const recsHtml =
    snapshot.recommendations.length === 0
      ? `<div class="empty">No pending recommendations.</div>`
      : snapshot.recommendations
          .slice(0, 4)
          .map(
            (rec) => `
        <div class="rec-row">
          <div class="account-meta">${rec.description}</div>
          ${rec.estimated_savings ? `<span class="badge success">${formatCurrency(rec.estimated_savings, "USD")}</span>` : ""}
        </div>`,
          )
          .join("");

  const usageHtml = avgUsage
    ? `
      <div class="usage-grid">
        <div class="usage-metric"><div class="label">CPU</div><div class="value">${formatPercent(avgUsage.cpu_usage_percent)}</div></div>
        <div class="usage-metric"><div class="label">Memory</div><div class="value">${formatMb(avgUsage.memory_usage_mb)}</div></div>
        <div class="usage-metric"><div class="label">Disk</div><div class="value">${formatMb(avgUsage.disk_usage_mb)}</div></div>
        <div class="usage-metric"><div class="label">Network</div><div class="value">${formatKbps(avgUsage.network_in_kbps + avgUsage.network_out_kbps)}</div></div>
      </div>`
    : `<div class="empty">No resource usage recorded yet.</div>`;

  const costHtml =
    costEntries.length === 0
      ? `<div class="empty">No billing entries this month.</div>`
      : costEntries.map(([currency, amount]) => `<span class="badge neutral">${formatCurrency(amount, currency)}</span>`).join(" ");

  container.innerHTML = `
    <div class="topbar">
      <h1>Cloud AI Platform Monitor</h1>
      <button class="icon-btn" id="settings-btn" title="Settings">⚙</button>
    </div>
    <div class="content">
      <div class="sync-time">Last synced: ${formatRelativeTime(lastSync)}</div>

      <div class="stat-row">
        <div class="stat"><div class="value">${snapshot.accounts.length}</div><div class="label">Accounts</div></div>
        <div class="stat"><div class="value">${snapshot.activeAlerts.alerts.length}</div><div class="label">Active alerts</div></div>
        <div class="stat critical"><div class="value">${snapshot.activeAlerts.criticalCount}</div><div class="label">Critical</div></div>
        <div class="stat warning"><div class="value">${snapshot.activeAlerts.warningCount}</div><div class="label">Warning</div></div>
      </div>

      <div class="section">
        <h2>Connected cloud accounts</h2>
        <div class="card">${accountsHtml}</div>
      </div>

      <div class="section">
        <h2>Resource usage summary</h2>
        <div class="card">${usageHtml}</div>
      </div>

      <div class="section">
        <h2>Cloud cost (this month)</h2>
        <div class="card">${costHtml}</div>
      </div>

      <div class="section">
        <h2>AI recommendations</h2>
        <div class="card">${recsHtml}</div>
      </div>

      <div class="section">
        <h2>Quick actions</h2>
        <div class="quick-actions">
          <button class="action" id="qa-refresh">Refresh monitoring</button>
          <button class="action" id="qa-connect">Connect cloud account</button>
          <button class="action" id="qa-alerts">View active alerts</button>
          <button class="action" id="qa-dashboard">Open dashboard</button>
          <button class="action" id="qa-reports">View reports</button>
          <button class="action" id="qa-notifications">Notification history</button>
        </div>
      </div>

      <button class="link" id="logout-btn">Log out</button>
    </div>
  `;

  container.querySelector<HTMLButtonElement>("#settings-btn")!.addEventListener("click", callbacks.onOpenSettings);
  container.querySelector<HTMLButtonElement>("#logout-btn")!.addEventListener("click", callbacks.onLogout);
  container.querySelector<HTMLButtonElement>("#qa-refresh")!.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "TRIGGER_POLL" });
    void renderDashboard(container, callbacks);
  });
  container.querySelector<HTMLButtonElement>("#qa-connect")!.addEventListener("click", () => openWebApp("/cloud-accounts"));
  container.querySelector<HTMLButtonElement>("#qa-alerts")!.addEventListener("click", () => openWebApp("/alerts"));
  container.querySelector<HTMLButtonElement>("#qa-dashboard")!.addEventListener("click", () => openWebApp("/dashboard"));
  // No dedicated "Reports" page exists in the web app - Optimization
  // (recommendations + estimated savings) is the closest existing
  // equivalent, so that's what this quick action opens.
  container.querySelector<HTMLButtonElement>("#qa-reports")!.addEventListener("click", () => openWebApp("/optimization"));
  container.querySelector<HTMLButtonElement>("#qa-notifications")!.addEventListener("click", () => openWebApp("/notifications"));
}
