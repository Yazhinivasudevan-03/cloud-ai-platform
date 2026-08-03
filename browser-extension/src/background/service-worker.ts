/** Background service worker (MV3). Responsibilities per the approved plan:
 * chrome.alarms-driven polling (never setInterval - it does not survive
 * service-worker suspension), badge updates, browser notifications on newly
 * -appeared active alerts, click-to-open the corresponding dashboard page,
 * and proactive token refresh (handled inside apiGet/ensureFreshAccessToken).
 * All state that must survive a suspend/wake cycle lives in
 * chrome.storage.local - nothing here relies on module-level variables
 * persisting between alarm ticks. */
import { fetchActiveAlerts } from "../shared/dashboard-data";
import {
  getLastSeenAlertIds,
  getLastSyncAt,
  getSettings,
  getTokens,
  setBadgeState,
  setLastSeenAlertIds,
  setLastSyncAt,
} from "../shared/storage";
import type { AlertRead } from "../shared/types";

const ALARM_NAME = "cloud-ai-poll";
const NOTIFICATION_TARGETS_KEY = "notification.targets";

async function setupAlarm(): Promise<void> {
  const settings = await getSettings();
  const periodInMinutes = Math.max(1, settings.refreshIntervalMinutes);
  await chrome.alarms.create(ALARM_NAME, { periodInMinutes });
}

async function updateBadge(criticalCount: number, warningCount: number): Promise<void> {
  await setBadgeState({ criticalCount, warningCount });
  if (criticalCount > 0) {
    await chrome.action.setBadgeText({ text: String(criticalCount) });
    await chrome.action.setBadgeBackgroundColor({ color: "#d32f2f" });
  } else if (warningCount > 0) {
    await chrome.action.setBadgeText({ text: String(warningCount) });
    await chrome.action.setBadgeBackgroundColor({ color: "#f9a825" });
  } else {
    await chrome.action.setBadgeText({ text: "" });
  }
}

function targetPathForAlert(alert: AlertRead): string {
  return alert.alert_type.startsWith("resource_optimization") ? "/optimization" : "/alerts";
}

async function notifyNewAlert(alert: AlertRead, soundEnabled: boolean): Promise<void> {
  const notificationId = `alert-${alert.id}`;
  const targets = await chrome.storage.local.get(NOTIFICATION_TARGETS_KEY);
  const map = (targets[NOTIFICATION_TARGETS_KEY] as Record<string, string>) ?? {};
  map[notificationId] = targetPathForAlert(alert);
  await chrome.storage.local.set({ [NOTIFICATION_TARGETS_KEY]: map });

  // chrome.notifications has no explicit mute/sound toggle in MV3 - priority
  // is the closest real, documented lever (higher priority is more likely to
  // play a sound/be prominent on desktop notification centers; it isn't a
  // guaranteed mute, and that's disclosed in docs/PHASE_32.md rather than
  // claimed as a real toggle).
  const basePriority = alert.severity === "critical" ? 2 : 1;
  await chrome.notifications.create(notificationId, {
    type: "basic",
    iconUrl: chrome.runtime.getURL("icons/icon128.png"),
    title: alert.severity === "critical" ? "Critical alert" : "Warning alert",
    message: alert.message,
    priority: soundEnabled ? basePriority : 0,
  });
}

export async function poll(): Promise<void> {
  const tokens = await getTokens();
  if (!tokens) {
    await updateBadge(0, 0);
    return;
  }

  const isFirstPoll = (await getLastSyncAt()) === null;

  let snapshot;
  try {
    snapshot = await fetchActiveAlerts();
  } catch {
    // Not logged in / backend unreachable this tick - leave the existing
    // badge/state alone rather than clobbering it with a false "all clear."
    return;
  }

  await updateBadge(snapshot.criticalCount, snapshot.warningCount);

  const settings = await getSettings();
  if (settings.notificationsEnabled && !isFirstPoll) {
    const lastSeen = await getLastSeenAlertIds();
    const newAlerts = snapshot.alerts.filter((a) => !lastSeen.has(a.id));
    for (const alert of newAlerts) {
      await notifyNewAlert(alert, settings.notificationSound);
    }
  }

  await setLastSeenAlertIds(new Set(snapshot.alerts.map((a) => a.id)));
  await setLastSyncAt(new Date().toISOString());
}

chrome.runtime.onInstalled.addListener(() => {
  void setupAlarm();
});

chrome.runtime.onStartup.addListener(() => {
  void setupAlarm();
  void poll();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) void poll();
});

chrome.notifications.onClicked.addListener(async (notificationId) => {
  const stored = await chrome.storage.local.get(NOTIFICATION_TARGETS_KEY);
  const map = (stored[NOTIFICATION_TARGETS_KEY] as Record<string, string>) ?? {};
  const path = map[notificationId] ?? "/alerts";
  const settings = await getSettings();
  await chrome.tabs.create({ url: `${settings.webAppBaseUrl}${path}` });
  await chrome.notifications.clear(notificationId);
});

chrome.runtime.onMessage.addListener((message: { type?: string }, _sender, sendResponse) => {
  if (message?.type === "TRIGGER_POLL") {
    void poll().then(() => sendResponse({ ok: true }));
    return true; // keep the message channel open for the async response
  }
  if (message?.type === "APPLY_SETTINGS") {
    void setupAlarm().then(() => sendResponse({ ok: true }));
    return true;
  }
  return false;
});
