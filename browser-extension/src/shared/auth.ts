/** Login/refresh/logout against the existing backend, using the exact same
 * wire format the web app already uses (frontend/src/services/authApi.ts,
 * httpClient.ts) - form-encoded login, refresh_token as a query param, no
 * new auth behavior invented here. */
import { clearTokens, getSettings, getTokens, setTokens } from "./storage";
import type { TokenPair, UserRead } from "./types";

export class AuthError extends Error {}

export async function login(username: string, password: string, rememberMe: boolean): Promise<TokenPair> {
  const settings = await getSettings();
  const body = new URLSearchParams({
    username,
    password,
    remember_me: String(rememberMe),
  });
  const response = await fetch(`${settings.backendBaseUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    if (response.status === 401) throw new AuthError("Incorrect username or password.");
    throw new AuthError(`Login failed (HTTP ${response.status}).`);
  }
  const tokens = (await response.json()) as TokenPair;
  await setTokens(tokens);
  return tokens;
}

export async function refreshTokens(): Promise<TokenPair | null> {
  const settings = await getSettings();
  const current = await getTokens();
  if (!current) return null;
  const url = `${settings.backendBaseUrl}/auth/refresh?refresh_token=${encodeURIComponent(current.refresh_token)}`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    await clearTokens();
    return null;
  }
  const tokens = (await response.json()) as TokenPair;
  await setTokens(tokens);
  return tokens;
}

export async function fetchCurrentUser(accessToken: string): Promise<UserRead | null> {
  const settings = await getSettings();
  const response = await fetch(`${settings.backendBaseUrl}/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) return null;
  return (await response.json()) as UserRead;
}

export async function logout(): Promise<void> {
  await clearTokens();
}

/** Reads the `exp` claim out of a JWT without verifying the signature - the
 * extension never needs to trust this locally, it's only used to decide
 * whether to proactively refresh before the backend would reject the token
 * anyway. A malformed token just looks "already expired," which is safe. */
export function getTokenExpiry(accessToken: string): number | null {
  try {
    const payload = accessToken.split(".")[1];
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

const REFRESH_BUFFER_MS = 60_000;

export async function ensureFreshAccessToken(): Promise<string | null> {
  const tokens = await getTokens();
  if (!tokens) return null;
  const expiry = getTokenExpiry(tokens.access_token);
  if (expiry !== null && expiry - Date.now() > REFRESH_BUFFER_MS) {
    return tokens.access_token;
  }
  const refreshed = await refreshTokens();
  return refreshed?.access_token ?? null;
}
