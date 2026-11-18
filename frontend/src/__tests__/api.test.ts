import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  exportAllDocuments,
  getAccessToken,
  getHealth,
  setAccessToken,
  setUnauthorizedRedirect,
} from "../api";

function jsonResponse(body: unknown, options: { ok?: boolean; status?: number; statusText?: string } = {}): Response {
  return {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    statusText: options.statusText ?? "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("api", () => {
  beforeEach(() => {
    localStorage.clear();
    setUnauthorizedRedirect(null);
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    localStorage.clear();
    setUnauthorizedRedirect(null);
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("utilise /api comme base par défaut", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getHealth()).resolves.toEqual({ status: "ok" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/health");
  });

  it("ajoute le token Bearer depuis localStorage", async () => {
    setAccessToken("token-123");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await getHealth();

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token-123");
  });

  it("supprime le token et redirige sur 401", async () => {
    setAccessToken("expired");
    const redirect = vi.fn();
    setUnauthorizedRedirect(redirect);
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ detail: "Invalid or expired credentials." }, { ok: false, status: 401, statusText: "Unauthorized" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getHealth()).rejects.toThrow(/401/);
    expect(getAccessToken()).toBeNull();
    expect(redirect).toHaveBeenCalledOnce();
  });

  it("appelle l'endpoint JSON d'export de la bibliothèque", async () => {
    const payload = { documents: [] };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(exportAllDocuments()).resolves.toEqual(payload);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/documents/export");
  });

  it("respecte VITE_API_BASE_URL", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok" }));
    vi.stubGlobal("fetch", fetchMock);
    const customApi = await import("../api");

    await customApi.getHealth();

    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example.test/health");
  });
});
