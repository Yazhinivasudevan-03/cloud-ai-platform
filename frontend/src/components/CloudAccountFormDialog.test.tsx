import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { CloudAccountFormDialog } from "./CloudAccountFormDialog";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import type { CloudProviderAccount } from "@/types";

// Real, non-mocked region data (frontend/src/utils/cloudRegions.ts) drives
// this dropdown - only the network-boundary API calls are mocked here,
// exactly like every other dialog test in this project.
vi.mock("@/services/cloudProviderAccountsApi", () => ({
  cloudProviderAccountsApi: {
    create: vi.fn(),
    update: vi.fn(),
    createTimezone: vi.fn(),
    testConnection: vi.fn(),
    // Fire-and-forget auto-validation after a successful save (Phase 26) -
    // resolves by default so its .catch(() => {}) never needs a real
    // implementation in tests that don't care about it.
    validateCredentials: vi.fn().mockResolvedValue({}),
  },
}));

function renderDialog(account: CloudProviderAccount | null = null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CloudAccountFormDialog open account={account} onClose={() => {}} />
    </QueryClientProvider>,
  );
}

describe("CloudAccountFormDialog - Region selection", () => {
  it("opens the Region dropdown with every AWS region visible and scrollable (default provider is AWS)", async () => {
    const user = userEvent.setup();
    renderDialog();

    const regionInput = screen.getByLabelText(/region/i);
    await user.click(regionInput);

    const listbox = await screen.findByRole("listbox");
    // A real, populated dropdown - not empty, not a stub. Spot-check a
    // handful of entries spread across the AWS table so this fails loudly
    // if the catalog import is broken or the array comes back empty.
    expect(within(listbox).getByText("us-east-1 — N. Virginia, United States")).toBeInTheDocument();
    expect(within(listbox).getByText("eu-west-2 — London, United Kingdom")).toBeInTheDocument();
    expect(within(listbox).getByText("ap-south-1 — Mumbai, India")).toBeInTheDocument();
    expect(within(listbox).getAllByRole("option").length).toBeGreaterThan(20);

    // A real scroll container, not a fixed-height div that just clips content.
    expect(listbox).toHaveStyle({ overflow: "auto" });
  });

  it("filters the dropdown by typing a location name", async () => {
    const user = userEvent.setup();
    renderDialog();

    const regionInput = screen.getByLabelText(/region/i);
    await user.click(regionInput);
    await user.type(regionInput, "London");

    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("eu-west-2 — London, United Kingdom")).toBeInTheDocument();
    expect(within(listbox).queryByText(/N\. Virginia/)).not.toBeInTheDocument();
  });

  it("filters the dropdown by typing a region code", async () => {
    const user = userEvent.setup();
    renderDialog();

    const regionInput = screen.getByLabelText(/region/i);
    await user.click(regionInput);
    await user.type(regionInput, "eu-central-1");

    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("eu-central-1 — Frankfurt, Germany")).toBeInTheDocument();
  });

  it("selecting a region shows the timezone that will be associated with it", async () => {
    const user = userEvent.setup();
    renderDialog();

    const regionInput = screen.getByLabelText(/region/i);
    await user.click(regionInput);
    await user.type(regionInput, "eu-west-2");
    await user.click(await screen.findByText("eu-west-2 — London, United Kingdom"));

    expect(await screen.findByText("Timezone will be set to Europe/London")).toBeInTheDocument();
  });

  it("reloads the Region dropdown to the newly selected provider's own regions", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByLabelText(/^provider$/i));
    await user.click(await screen.findByRole("option", { name: "Azure" }));

    const regionInput = screen.getByLabelText(/region/i);
    await user.click(regionInput);

    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("uksouth — UK South (London)")).toBeInTheDocument();
    expect(within(listbox).queryByText(/us-east-1/)).not.toBeInTheDocument();
  });

  it("auto-associates the matched region's timezone when the account is saved", async () => {
    const user = userEvent.setup();
    vi.mocked(cloudProviderAccountsApi.create).mockResolvedValue({
      id: 42,
      user_id: 1,
      provider: "aws",
      account_name: "Prod AWS",
      region: "eu-west-2",
      account_identifier: null,
      is_active: true,
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
      credentials_validated: false,
      credentials_validated_at: null,
    });
    vi.mocked(cloudProviderAccountsApi.createTimezone).mockResolvedValue({
      id: 1,
      cloud_provider_account_id: 42,
      provider: "aws",
      region: "eu-west-2",
      availability_zone: null,
      label: "London, United Kingdom",
      timezone: "Europe/London",
      utc_offset: "+00:00",
      current_local_time: "2026-01-01T00:00:00",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    });

    renderDialog();

    await user.type(screen.getByLabelText(/account name/i), "Prod AWS");
    const regionInput = screen.getByLabelText(/region/i);
    await user.click(regionInput);
    await user.type(regionInput, "eu-west-2");
    await user.click(await screen.findByText("eu-west-2 — London, United Kingdom"));
    await user.type(screen.getByLabelText("AWS Access Key ID"), "access_key_id");
    await user.type(screen.getByLabelText("AWS Secret Access Key"), "secret");

    await user.click(screen.getByRole("button", { name: "Add" }));

    await vi.waitFor(() => expect(cloudProviderAccountsApi.create).toHaveBeenCalled());
    await vi.waitFor(() =>
      expect(cloudProviderAccountsApi.createTimezone).toHaveBeenCalledWith(42, {
        region: "eu-west-2",
        label: "London, United Kingdom",
        timezone: "Europe/London",
      }),
    );
  });
});
