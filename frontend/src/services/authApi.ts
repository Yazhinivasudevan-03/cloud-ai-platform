import { httpClient } from "./httpClient";
import type {
  ChangePasswordPayload,
  EmailVerificationResult,
  MessageResponse,
  RegisterPayload,
  RegisterResponse,
  TokenPair,
  User,
  UserProfileUpdate,
} from "@/types";

export type { RegisterPayload };

export const authApi = {
  register: (payload: RegisterPayload) =>
    httpClient.post<RegisterResponse>("/auth/register", payload).then((r) => r.data),

  login: (identifier: string, password: string, rememberMe = false) => {
    const form = new URLSearchParams();
    form.set("username", identifier);
    form.set("password", password);
    form.set("remember_me", String(rememberMe));
    return httpClient
      .post<TokenPair>("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      })
      .then((r) => r.data);
  },

  me: () => httpClient.get<User>("/auth/me").then((r) => r.data),

  updateMe: (payload: UserProfileUpdate) =>
    httpClient.patch<User>("/auth/me", payload).then((r) => r.data),

  changePassword: (payload: ChangePasswordPayload) =>
    httpClient.post<MessageResponse>("/auth/change-password", payload).then((r) => r.data),

  verifyEmail: (token: string) =>
    httpClient
      .get<EmailVerificationResult>("/auth/verify-email", { params: { token } })
      .then((r) => r.data),

  resendVerification: (email: string) =>
    httpClient
      .post<EmailVerificationResult>("/auth/resend-verification", { email })
      .then((r) => r.data),

  forgotPassword: (email: string) =>
    httpClient.post<MessageResponse>("/auth/forgot-password", { email }).then((r) => r.data),

  resetPassword: (token: string, newPassword: string, confirmNewPassword: string) =>
    httpClient
      .post<MessageResponse>("/auth/reset-password", {
        token,
        new_password: newPassword,
        confirm_new_password: confirmNewPassword,
      })
      .then((r) => r.data),
};
