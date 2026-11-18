import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../state/AuthContext";
import LoginPage from "../pages/LoginPage";

const mocks = vi.hoisted(() => ({
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
  login: vi.fn(),
  logoutAuth: vi.fn(),
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  setUnauthorizedRedirect: vi.fn(),
}));

vi.mock("../api", () => ({
  BASE: "/api",
  TOKEN_KEY: "sd_access_token",
  ENDPOINTS: {},
  ...mocks,
}));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Page protégée</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.getAuthStatus.mockResolvedValue({ enabled: true, bootstrapped: false });
    mocks.getAccessToken.mockReturnValue(null);
    mocks.login.mockResolvedValue({
      access_token: "token-456",
      token_type: "bearer",
      expires_at: "2026-11-18T00:00:00Z",
      user: {
        id: 1,
        email: "admin@example.com",
        full_name: "Admin",
        role: "admin",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });
  });

  it("affiche l'état réel du backend et connecte l'utilisateur", async () => {
    renderLogin();

    expect(await screen.findByText("Connexion")).toBeInTheDocument();
    expect(screen.getByText(/Aucun compte n’existe encore/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));

    await waitFor(() => expect(screen.getByText("Page protégée")).toBeInTheDocument());
    expect(mocks.login).toHaveBeenCalledWith({ email: "admin@example.com", password: "password123" });
    expect(mocks.setAccessToken).toHaveBeenCalledWith("token-456");
  });

  it("affiche une erreur réelle quand le backend refuse la connexion", async () => {
    mocks.login.mockRejectedValueOnce(new Error("Erreur API 401 : Invalid email or password."));
    renderLogin();

    const email = await screen.findByLabelText("Adresse e-mail");
    fireEvent.change(email, { target: { value: "admin@example.com" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(screen.getByText("Connexion")).toBeInTheDocument();
  });
});
