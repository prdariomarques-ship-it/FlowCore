import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = vi.hoisted(() => ({ getItem: vi.fn(), setItem: vi.fn() }));

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: storage,
}));

import { getMarketNews } from "../lib/flowcore";
import type { MarketNewsItem } from "../lib/flowcore";
import { filterNewsItems, loadNewsFavorites, persistNewsFavorites } from "../lib/news-favorites";

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

  it("filtra títulos, fontes e ativos sem depender de nova consulta", () => {
    const item: MarketNewsItem = {
      id: "news-1", headline: "Inflação brasileira desacelera", section_tags: ["brasil"], category: "inflation",
      related_region: "brazil", publisher: "Fonte de teste", provider: { id: "yahoo_finance", name: "Yahoo Finance", url: "https://finance.yahoo.com/" },
      canonical_url: "https://example.com/news-1", published_at: "2026-08-25T12:00:00Z", collected_at: "2026-08-25T12:01:00Z", related_assets: ["^BVSP"], status: "ok",
    };
    expect(filterNewsItems([item], "INFLACAO")).toHaveLength(1);
    expect(filterNewsItems([item], "bvsp")).toHaveLength(1);
    expect(filterNewsItems([item], "inexistente")).toHaveLength(0);
  });

  it("restaura e persiste leituras favoritas localmente", async () => {
    const favorite: MarketNewsItem = {
      id: "fav-1", headline: "Leitura posterior", section_tags: ["ia"], category: "technology", related_region: "us",
      publisher: "Fonte", provider: { id: "yahoo_finance", name: "Yahoo Finance", url: "https://finance.yahoo.com/" }, canonical_url: "https://example.com/fav",
      published_at: "2026-08-25T12:00:00Z", collected_at: "2026-08-25T12:01:00Z", related_assets: ["^IXIC"], status: "ok",
    };
    storage.getItem.mockResolvedValue(JSON.stringify([favorite]));
    await expect(loadNewsFavorites()).resolves.toEqual({ "fav-1": favorite });
    await persistNewsFavorites({ "fav-1": favorite });
    expect(storage.setItem).toHaveBeenCalledWith("flowcore.news.favorites.v1", JSON.stringify([favorite]));
  });
});
