import { httpClient } from "./httpClient";
import type { PaginatedResponse, User } from "@/types";

export const usersApi = {
  list: (page: number, pageSize: number) =>
    httpClient
      .get<PaginatedResponse<User>>("/users", { params: { page, page_size: pageSize } })
      .then((r) => r.data),

  get: (userId: number) => httpClient.get<User>(`/users/${userId}`).then((r) => r.data),

  assignRole: (userId: number, roleName: string) =>
    httpClient.post<User>(`/users/${userId}/roles`, { role_name: roleName }).then((r) => r.data),

  removeRole: (userId: number, roleName: string) =>
    httpClient.delete<User>(`/users/${userId}/roles/${roleName}`).then((r) => r.data),
};
