import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NotificationSettingsPage } from "./NotificationSettingsPage";
import { notificationSettingsApi } from "@/services/notificationSettingsApi";
import { useAuth } from "@/contexts/AuthContext";
import { SIMPLE_ALERT_CATEGORIES, TIERED_ALERT_CATEGORIES, type AlertCategoryPreference, type NotificationSetting } from "@/types";

const DEFAULT_ALERT_PREFERENCES = Object.fromEntries(
  [...TIERED_ALERT_CATEGORIES, ...SIMPLE_ALERT_CATEGORIES].map((category) => [
    category,
    { enabled: true, warning: true, critical: true, saturated: true } satisfies AlertCategoryPreference,
  ]),
) as NotificationSetting["alert_preferences"];

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/services/notificationSettingsApi", () => ({
  notificationSettingsApi: {
    get: vi.fn(),
    update: vi.fn(),
    sendTest: vi.fn(),
  },
}));

const DEFAULT_SETTINGS: NotificationSetting = {
  email_enabled: true,
  sms_enabled: false,
  telegram_enabled: false,
  slack_enabled: false,
  teams_enabled: false,
  instant_alerts_enabled: true,
  daily_summary_enabled: false,
  alert_sound_enabled: true,
  dnd_start_time: null,
  dnd_end_time: null,
  timezone: "UTC",
  telegram_bot_token_configured: false,
  telegram_chat_id_configured: false,
  slack_webhook_configured: false,
  teams_webhook_configured: false,
  secondary_email: null,
  country_code: null,
  telegram_username: null,
  notification_language: "en",
  alert_preferences: DEFAULT_ALERT_PREFERENCES,
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotificationSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationSettingsPage", () => {
  it("loads and displays the current channel state", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 1, username: "jdoe", email: "jdoe@example.com", full_name: null, phone_number: null, is_active: true, is_superuser: false, roles: [] },
      refreshCurrentUser: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    vi.mocked(notificationSettingsApi.get).mockResolvedValue(DEFAULT_SETTINGS);

    renderPage();

    expect(await screen.findByText("Channels")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Email" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "SMS" })).not.toBeChecked();
  });

  it("saves the updated channel toggles", async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 1, username: "jdoe", email: "jdoe@example.com", full_name: null, phone_number: null, is_active: true, is_superuser: false, roles: [] },
      refreshCurrentUser: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    vi.mocked(notificationSettingsApi.get).mockResolvedValue(DEFAULT_SETTINGS);
    vi.mocked(notificationSettingsApi.update).mockResolvedValue({ ...DEFAULT_SETTINGS, slack_enabled: true });
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Channels");

    await user.click(screen.getByRole("checkbox", { name: "Slack" }));
    await user.click(screen.getByRole("button", { name: "Save configuration" }));

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(notificationSettingsApi.update).toHaveBeenCalledWith(
      expect.objectContaining({ slack_enabled: true }),
    );
  });
});
