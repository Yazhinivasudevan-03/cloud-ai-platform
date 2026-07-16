import { httpClient } from "./httpClient";
import type { Notification, PaginatedResponse } from "@/types";

export const notificationsApi = {
  listMine: (page = 1, pageSize = 20, isRead?: boolean) =>
    httpClient
      .get<PaginatedResponse<Notification>>("/notifications", {
        params: { page, page_size: pageSize, is_read: isRead },
      })
      .then((r) => r.data),

  markRead: (notificationId: number) =>
    httpClient.patch<Notification>(`/notifications/${notificationId}/read`).then((r) => r.data),
};
