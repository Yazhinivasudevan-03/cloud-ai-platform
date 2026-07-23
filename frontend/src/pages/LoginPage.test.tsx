import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";
import { useAuth } from "@/contexts/AuthContext";

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Home page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  it("logs in and navigates to the originally-requested page on success", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({ login } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), "jdoe");
    await user.type(screen.getByLabelText(/password/i), "Sup3rSecret!");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(login).toHaveBeenCalledWith("jdoe", "Sup3rSecret!");
    expect(await screen.findByText("Home page")).toBeInTheDocument();
  });

  it("shows an error message and stays on the page when login fails", async () => {
    const login = vi.fn().mockRejectedValue(new Error("invalid credentials"));
    vi.mocked(useAuth).mockReturnValue({ login } as unknown as ReturnType<typeof useAuth>);
    const user = userEvent.setup();

    renderLoginPage();

    await user.type(screen.getByLabelText(/username/i), "jdoe");
    await user.type(screen.getByLabelText(/password/i), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByText("An unexpected error occurred")).toBeInTheDocument();
    expect(screen.queryByText("Home page")).not.toBeInTheDocument();
  });
});
