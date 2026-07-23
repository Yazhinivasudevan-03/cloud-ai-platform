import { httpClient } from "./httpClient";
import type {
  NotificationSetting,
  NotificationSettingTestResult,
  NotificationSettingUpdate,
} from "@/types";

export const notificationSettingsApi = {
  get: () => httpClient.get<NotificationSetting>("/notification-settings").then((r) => r.data),

  update: (payload: NotificationSettingUpdate) =>
    httpClient.put<NotificationSetting>("/notification-settings", payload).then((r) => r.data),

  sendTest: () =>
    httpClient
      .post<NotificationSettingTestResult>("/notification-settings/test")
      .then((r) => r.data),
};
