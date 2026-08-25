import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: {
    getItem: vi.fn(async (key: string) => store.get(key) ?? null),
    setItem: vi.fn(async (key: string, value: string) => { store.set(key, value); }),
  },
}));

import { checkConnection, defaultSettings, formatDelta, formatNumber, loadSettings, saveSettings } from "../lib/flowcore";

describe("cliente FlowCore", () => {
  beforeEach(() => {
    store.clear();
    vi.unstubAllGlobals();
  });

  it("persiste apenas URLs e preferência de rota", async () => {
    await saveSettings({ publicUrl: "https://public.example/", privateUrl: "https://private.example/", preference: "tailscale" });
    await expect(loadSettings()).resolves.toEqual({ publicUrl: "https://public.example", privateUrl: "https://private.example", preference: "tailscale" });
  });

  it("prioriza Tailscale no modo privado e volta ao Cloudflare quando a rota privada falha", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error("private unavailable"))
      .mockResolvedValueOnce({ ok: true, json: async () => ({ version: "1.5.0" }) });
    vi.stubGlobal("fetch", fetchMock);
    const state = await checkConnection({ publicUrl: "https://public.example", privateUrl: "https://private.example", preference: "tailscale" });
    expect(state.reachable).toBe(true);
    expect(state.source).toBe("cloudflare");
    expect(fetchMock.mock.calls[0][0]).toBe("https://private.example/api/health");
    expect(fetchMock.mock.calls[1][0]).toBe("https://public.example/api/health");
  });

  it("mantém ausência de cotação explícita e exibe variação com sinal", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatDelta(null)).toBe("—");
    expect(formatDelta(1.25)).toBe("+1,25%");
    expect(formatDelta(-0.4)).toBe("-0,4%");
    expect(defaultSettings.publicUrl).toBe("https://flowcore.admissaoazusa.com.br");
  });
});
