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

describe("api v2 contract", () => {
  beforeEach(() => { vi.resetModules(); vi.unstubAllEnvs(); });
  afterEach(() => vi.unstubAllGlobals());

  it("serialise les filtres de /components en query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0, page: 1, page_size: 24 }));
    vi.stubGlobal("fetch", fetchMock);
    const { listComponents } = await import("../api");
    await listComponents({ q: "LM358", manufacturer: "TI", category: undefined, page: 2, page_size: 24 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/components?q=LM358&manufacturer=TI&page=2&page_size=24");
  });

  it("refuse une comparaison hors de 2 à 5 composants sans appeler le réseau", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    const { compareComponents } = await import("../api");
    await expect(compareComponents([1])).rejects.toThrow();
    await expect(compareComponents([1, 2, 3, 4, 5, 6])).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
    await compareComponents([1, 2]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/compare");
    expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)).toEqual({ component_ids: [1, 2] });
  });

  it("appelle les endpoints de revue de spécification", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 9 }));
    vi.stubGlobal("fetch", fetchMock);
    const { acceptSpec, rejectSpec, editSpec, addSpec } = await import("../api");
    await acceptSpec(9, "ok");
    await rejectSpec(9);
    await editSpec(9, { value_text: "3.3" });
    await addSpec(4, { parameter: "vcc", category: "electrical", condition_type: "general", value_text: "5" });
    const calls = fetchMock.mock.calls.map((c) => [c[0], (c[1] as RequestInit).method]);
    expect(calls).toEqual([
      ["/api/specs/9/accept", "POST"],
      ["/api/specs/9/reject", "POST"],
      ["/api/specs/9", "PATCH"],
      ["/api/components/4/specs", "POST"],
    ]);
  });
});
