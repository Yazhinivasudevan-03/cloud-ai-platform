/** Typed chrome.storage.local access. Everything the extension persists
 * lives here - tokens, settings, and the small poll-state cache the
 * background service worker needs to survive being suspended between
 * chrome.alarms ticks (MV3 service workers are ephemeral; module-level
 * variables do not survive a wake-up, only chrome.storage does). */
import type { ExtensionSettings, TokenPair } from "./types";
import { DEFAULT_SETTINGS } from "./types";

const KEYS = {
  accessToken: "auth.access_token",
  refreshToken: "auth.refresh_token",
  settings: "settings",
  lastSeenAlertIds: "poll.last_seen_alert_ids",
  lastSyncAt: "poll.last_sync_at",
  badgeState: "poll.badge_state",
} as const;

export async function getTokens(): Promise<TokenPair | null> {
  const stored = await chrome.storage.local.get([KEYS.accessToken, KEYS.refreshToken]);
  const access_token = stored[KEYS.accessToken] as string | undefined;
  const refresh_token = stored[KEYS.refreshToken] as string | undefined;
  if (!access_token || !refresh_token) return null;
  return { access_token, refresh_token, token_type: "bearer" };
}

export async function setTokens(tokens: TokenPair): Promise<void> {
  await chrome.storage.local.set({
    [KEYS.accessToken]: tokens.access_token,
    [KEYS.refreshToken]: tokens.refresh_token,
  });
}

export async function clearTokens(): Promise<void> {
  await chrome.storage.local.remove([KEYS.accessToken, KEYS.refreshToken]);
}

export async function getSettings(): Promise<ExtensionSettings> {
  const stored = await chrome.storage.local.get(KEYS.settings);
  const saved = stored[KEYS.settings] as Partial<ExtensionSettings> | undefined;
  return { ...DEFAULT_SETTINGS, ...saved };
}

export async function setSettings(settings: ExtensionSettings): Promise<void> {
  await chrome.storage.local.set({ [KEYS.settings]: settings });
}

export async function getLastSeenAlertIds(): Promise<Set<number>> {
  const stored = await chrome.storage.local.get(KEYS.lastSeenAlertIds);
  const ids = stored[KEYS.lastSeenAlertIds] as number[] | undefined;
  return new Set(ids ?? []);
}

export async function setLastSeenAlertIds(ids: Set<number>): Promise<void> {
  await chrome.storage.local.set({ [KEYS.lastSeenAlertIds]: Array.from(ids) });
}

export async function setLastSyncAt(iso: string): Promise<void> {
  await chrome.storage.local.set({ [KEYS.lastSyncAt]: iso });
}

export async function getLastSyncAt(): Promise<string | null> {
  const stored = await chrome.storage.local.get(KEYS.lastSyncAt);
  return (stored[KEYS.lastSyncAt] as string | undefined) ?? null;
}

export interface BadgeState {
  criticalCount: number;
  warningCount: number;
}

export async function setBadgeState(state: BadgeState): Promise<void> {
  await chrome.storage.local.set({ [KEYS.badgeState]: state });
}

export async function getBadgeState(): Promise<BadgeState> {
  const stored = await chrome.storage.local.get(KEYS.badgeState);
  return (stored[KEYS.badgeState] as BadgeState | undefined) ?? { criticalCount: 0, warningCount: 0 };
}
