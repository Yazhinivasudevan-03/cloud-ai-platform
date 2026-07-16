import { httpClient } from "./httpClient";
import type { TokenPair, User } from "@/types";

export interface RegisterPayload {
  username: string;
  email: string;
  full_name?: string;
  password: string;
}

export const authApi = {
  register: (payload: RegisterPayload) =>
    httpClient.post<User>("/auth/register", payload).then((r) => r.data),

  login: (username: string, password: string) => {
    const form = new URLSearchParams();
    form.set("username", username);
    form.set("password", password);
    return httpClient
      .post<TokenPair>("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      })
      .then((r) => r.data);
  },

  me: () => httpClient.get<User>("/auth/me").then((r) => r.data),
};
