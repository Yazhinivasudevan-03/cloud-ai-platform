import { httpClient } from "./httpClient";
import type { TimezoneValidationResult } from "@/types";

export const timezonesApi = {
  list: () => httpClient.get<string[]>("/timezones").then((r) => r.data),

  validate: (timezone: string) =>
    httpClient
      .post<TimezoneValidationResult>("/timezones/validate", null, { params: { timezone } })
      .then((r) => r.data),
};
