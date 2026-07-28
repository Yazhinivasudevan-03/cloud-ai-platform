import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { ApiErrorBody, TokenPair } from "@/types";

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

/** Key used for a validation error that isn't tied to a single field (e.g.
 * an unrecognized cross-field check) - callers that can't map it to a
 * specific input should fall back to showing it as a general error. */
export const FORM_ERROR_KEY = "_form";

/** Parses a 422 response's `error.details` (a Pydantic/FastAPI validation
 * error list - see app/middleware/error_handler.py) into a field-name ->
 * message map, so a form can show each error directly under its own
 * input instead of one generic banner. Returns {} for any non-validation
 * error (e.g. a 409 conflict, a network failure) - callers should fall
 * back to `extractErrorMessage` in that case. */
export function extractFieldErrors(error: unknown): Record<string, string> {
  if (!axios.isAxiosError(error)) return {};
  const body = error.response?.data as ApiErrorBody | undefined;
  const details = body?.error?.details;
  if (!Array.isArray(details)) return {};

  const fieldErrors: Record<string, string> = {};
  for (const detail of details) {
    const loc = Array.isArray(detail.loc) ? detail.loc.filter((part) => part !== "body") : [];
    const field = loc.length > 0 ? String(loc[0]) : null;
    const message =
      detail.type === "missing" && field
        ? `Missing required field: ${field}`
        : (detail.msg ?? "").replace(/^Value error,\s*/, "");

    if (field) {
      fieldErrors[field] = message;
      continue;
    }

    // A model-level (cross-field) validator error - e.g. confirm_password
    // not matching password - has no single field in its `loc`, so map
    // known message content to the field that's actually wrong, rather
    // than dropping it into a form-wide fallback where it's less useful.
    if (message.includes("confirm_new_password")) {
      fieldErrors.confirm_new_password = "Confirm password does not match";
    } else if (message.includes("confirm_password")) {
      fieldErrors.confirm_password = "Confirm password does not match";
    } else {
      fieldErrors[FORM_ERROR_KEY] = message;
    }
  }
  return fieldErrors;
}
