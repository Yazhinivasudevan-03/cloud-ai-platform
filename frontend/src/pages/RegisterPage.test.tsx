import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, AxiosHeaders } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RegisterPage } from "./RegisterPage";
import { useAuth } from "@/contexts/AuthContext";

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={["/register"]}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Builds the same AxiosError shape the real backend returns for a 422
 * (see app/middleware/error_handler.py) - a real, specific top-level
 * `message` plus a structured `details` array, exactly what
 * extractFieldErrors() parses. */
function make422Error(message: string, details: object[]) {
  return new AxiosError(
    message,
    "ERR_BAD_REQUEST",
    { headers: new AxiosHeaders() },
    undefined,
    {
      status: 422,
      statusText: "Unprocessable Entity",
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: { error: { code: "VALIDATION_ERROR", message, details } },
    },
  );
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/first name/i), "Ada");
  await user.type(screen.getByLabelText(/last name/i), "Lovelace");
  await user.type(screen.getByLabelText(/^email/i), "ada@example.com");
  await user.type(screen.getByLabelText(/phone number/i), "(415) 555-2671");
  await user.type(screen.getByLabelText(/^country/i), "US");
  await user.type(screen.getByLabelText(/^password/i), "weakpass");
  await user.type(screen.getByLabelText(/confirm password/i), "weakpass");
}

describe("RegisterPage", () => {
  it("shows the real backend validation message directly under the phone number field, not a generic banner", async () => {
    const register = vi.fn().mockRejectedValue(
      make422Error("mobile_number must be in E.164 format, e.g. +14155552671", [
        {
          type: "value_error",
          loc: ["body", "mobile_number"],
          msg: "Value error, mobile_number must be in E.164 format, e.g. +14155552671",
        },
      ]),
    );
    vi.mocked(useAuth).mockReturnValue({ register } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText("mobile_number must be in E.164 format, e.g. +14155552671"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Request validation failed")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/phone number/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("maps a confirm_password model-level error to the confirm password field", async () => {
    const register = vi.fn().mockRejectedValue(
      make422Error("password and confirm_password must match", [
        {
          type: "value_error",
          loc: ["body"],
          msg: "Value error, password and confirm_password must match",
        },
      ]),
    );
    vi.mocked(useAuth).mockReturnValue({ register } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Confirm password does not match")).toBeInTheDocument();
    expect(screen.queryByText("Request validation failed")).not.toBeInTheDocument();
  });

  it("shows a missing-required-field message under the right input", async () => {
    const register = vi.fn().mockRejectedValue(
      make422Error("Missing required field: country", [
        { type: "missing", loc: ["body", "country"], msg: "Field required" },
      ]),
    );
    vi.mocked(useAuth).mockReturnValue({ register } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Missing required field: country")).toBeInTheDocument();
  });

  it("falls back to the generic error banner for a non-field error like an email conflict", async () => {
    const conflictError = new AxiosError(
      "A user with this username or email already exists",
      "ERR_BAD_REQUEST",
      { headers: new AxiosHeaders() },
      undefined,
      {
        status: 409,
        statusText: "Conflict",
        headers: {},
        config: { headers: new AxiosHeaders() },
        data: { error: { code: "USER_EXISTS", message: "A user with this username or email already exists" } },
      },
    );
    const register = vi.fn().mockRejectedValue(conflictError);
    vi.mocked(useAuth).mockReturnValue({ register } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText("A user with this username or email already exists"),
    ).toBeInTheDocument();
  });

  it("clears a field's error as soon as the user edits it", async () => {
    const register = vi.fn().mockRejectedValue(
      make422Error("mobile_number must be in E.164 format, e.g. +14155552671", [
        {
          type: "value_error",
          loc: ["body", "mobile_number"],
          msg: "Value error, mobile_number must be in E.164 format, e.g. +14155552671",
        },
      ]),
    );
    vi.mocked(useAuth).mockReturnValue({ register } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(
      await screen.findByText("mobile_number must be in E.164 format, e.g. +14155552671"),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText(/phone number/i), "1");

    expect(
      screen.queryByText("mobile_number must be in E.164 format, e.g. +14155552671"),
    ).not.toBeInTheDocument();
  });

  it("shows the check-your-email screen with the real verification link on success", async () => {
    const register = vi.fn().mockResolvedValue({
      id: 1,
      username: "ada",
      email: "ada@example.com",
      verification_token: "real-token-abc",
      verification_link: "http://localhost:3000/verify-email?token=real-token-abc",
    });
    vi.mocked(useAuth).mockReturnValue({ register } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderRegisterPage();
    await fillValidForm(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /verify my email/i })).toHaveAttribute(
      "href",
      "/verify-email?token=real-token-abc",
    );
  });
});
