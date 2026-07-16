import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { TokenPair } from "@/types";

const ACCESS_TOKEN_KEY = "cloud-ai-platform.access_token";
const REFRESH_TOKEN_KEY = "cloud-ai-platform.refresh_token";

export const tokenStorage = {
  getAccessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  setTokens: (tokens: TokenPair) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const httpClient = axios.create({ baseURL });

httpClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.getAccessToken();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

/** Callback the app registers to force a redirect to /login once a token
 * refresh has failed - kept decoupled from this module (which has no
 * knowledge of routing) via a simple setter, avoiding a circular import
 * between the HTTP client and the auth context. */
let onAuthFailure: (() => void) | null = null;
export function registerAuthFailureHandler(handler: () => void) {
  onAuthFailure = handler;
}

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) return null;

  try {
    const response = await axios.post<TokenPair>(
      `${baseURL}/auth/refresh`,
      null,
      { params: { refresh_token: refreshToken } },
    );
    tokenStorage.setTokens(response.data);
    return response.data.access_token;
  } catch {
    return null;
  }
}

httpClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;

    if (error.response?.status === 401 && originalRequest && !originalRequest._retried) {
      originalRequest._retried = true;

      refreshInFlight ??= refreshAccessToken().finally(() => {
        refreshInFlight = null;
      });
      const newAccessToken = await refreshInFlight;

      if (newAccessToken) {
        originalRequest.headers.set("Authorization", `Bearer ${newAccessToken}`);
        return httpClient(originalRequest);
      }

      tokenStorage.clear();
      onAuthFailure?.();
    }

    return Promise.reject(error);
  },
);

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as { error?: { message?: string } } | undefined;
    if (body?.error?.message) return body.error.message;
    if (error.message) return error.message;
  }
  return "An unexpected error occurred";
}
