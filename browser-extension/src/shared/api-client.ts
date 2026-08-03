/** Authenticated GET wrapper for every regular API call the extension makes
 * (everything except login/refresh themselves - see auth.ts). Mirrors
 * httpClient.ts's proven 401 -> refresh-once -> retry pattern, adapted for
 * chrome.storage.local instead of localStorage/axios interceptors. */
import { ensureFreshAccessToken, refreshTokens } from "./auth";
import { getSettings } from "./storage";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

type QueryValue = string | number | boolean | undefined;

function buildUrl(base: string, path: string, params?: Record<string, QueryValue>): string {
  const url = new URL(`${base}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function requestWithToken(url: string, accessToken: string): Promise<Response> {
  return fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });
}

export async function apiGet<T>(path: string, params?: Record<string, QueryValue>): Promise<T> {
  const settings = await getSettings();
  const url = buildUrl(settings.backendBaseUrl, path, params);

  let accessToken = await ensureFreshAccessToken();
  if (!accessToken) throw new ApiError("Not logged in.", 401);

  let response = await requestWithToken(url, accessToken);

  if (response.status === 401) {
    const refreshed = await refreshTokens();
    if (!refreshed) throw new ApiError("Session expired - please log in again.", 401);
    accessToken = refreshed.access_token;
    response = await requestWithToken(url, accessToken);
  }

  if (!response.ok) {
    let detail = `Request to ${path} failed (HTTP ${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body - keep the generic message */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}
