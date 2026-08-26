import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = vi.hoisted(() => ({ getItem: vi.fn(), setItem: vi.fn() }));

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: storage,
}));

import { getMarketNews } from "../lib/flowcore";

describe("getMarketNews", () => {
  beforeEach(() => {
    storage.getItem.mockReset();
    storage.setItem.mockReset();
    storage.getItem.mockResolvedValue(null);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [{
          id: "news-1", headline: "Notícia de teste", section_tags: ["brasil"], category: "brazil",
          related_region: "brazil", publisher: "Fonte de teste",
          provider: { id: "yahoo_finance", name: "Yahoo Finance", url: "https://finance.yahoo.com/" },
          canonical_url: "https://example.com/news-1", published_at: "2026-08-25T12:00:00Z",
          collected_at: "2026-08-25T12:01:00Z", related_assets: ["^BVSP"], status: "ok",
        }],
        groups: ["brazil"], section: "brasil", supported_sections: ["all", "brasil"],
        next_cursor: "5", partial_errors: [], available: true, source: "yahoo_finance",
      }),
    }));
  });

  it("solicita uma página com filtro, cursor e fonte preservada", async () => {
    const response = await getMarketNews("brasil", "2", 5);

    expect(fetch).toHaveBeenCalledWith(
      "https://flowcore.admissaoazusa.com.br/api/market/news?section=brasil&limit=5&cursor=2",
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
    expect(response.source).toBe("cloudflare");
    expect(response.data.next_cursor).toBe("5");
    expect(response.data.items[0]).toMatchObject({
      provider: { id: "yahoo_finance" },
      canonical_url: "https://example.com/news-1",
      related_assets: ["^BVSP"],
    });
  });
});
