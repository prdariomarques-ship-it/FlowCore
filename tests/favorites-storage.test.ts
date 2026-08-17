import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = vi.hoisted(() => ({
  getItem: vi.fn(),
  setItem: vi.fn(),
}));

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: storage,
}));

import { loadFavoriteSlugs, saveFavoriteSlugs } from "../lib/favorites-storage";

describe("persistência de favoritos", () => {
  beforeEach(() => {
    storage.getItem.mockReset();
    storage.setItem.mockReset();
    storage.setItem.mockResolvedValue(undefined);
  });

  it("carrega, normaliza e protege o catálogo contra dados locais inválidos", async () => {
    storage.getItem.mockResolvedValue('["paulo-de-tarso", "", "calvino", "calvino"]');

    await expect(loadFavoriteSlugs()).resolves.toEqual(["paulo-de-tarso", "calvino"]);

    storage.getItem.mockRejectedValueOnce(new Error("storage indisponível"));
    await expect(loadFavoriteSlugs()).resolves.toEqual([]);
  });

  it("persiste a lista normalizada usando a chave exclusiva do catálogo", async () => {
    await saveFavoriteSlugs(["paulo-de-tarso", "", "paulo-de-tarso", "calvino"]);

    expect(storage.setItem).toHaveBeenCalledWith(
      "teologos.favorite-theologians",
      '["paulo-de-tarso","calvino"]',
    );
  });
});
