import { httpClient } from "./httpClient";
import type { Notification, NotificationSummary, PaginatedResponse } from "@/types";

export const notificationsApi = {
  listMine: (page = 1, pageSize = 20, isRead?: boolean) =>
    httpClient
      .get<PaginatedResponse<Notification>>("/notifications", {
        params: { page, page_size: pageSize, is_read: isRead },
      })
      .then((r) => r.data),

  summary: () => httpClient.get<NotificationSummary>("/notifications/summary").then((r) => r.data),

  markRead: (notificationId: number) =>
    httpClient.patch<Notification>(`/notifications/${notificationId}/read`).then((r) => r.data),

  remove: (notificationId: number) =>
    httpClient.delete(`/notifications/${notificationId}`).then(() => undefined),
};
