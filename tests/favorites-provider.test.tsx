import React from "react";
import { act, create } from "react-test-renderer";
import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = vi.hoisted(() => ({
  getItem: vi.fn(),
  setItem: vi.fn(),
}));

vi.mock("@react-native-async-storage/async-storage", () => ({
  default: storage,
}));

import { FavoritesProvider, useFavorites } from "../lib/favorites-provider";

let favoriteState: ReturnType<typeof useFavorites> | null = null;

function FavoritesProbe() {
  favoriteState = useFavorites();
  return null;
}

async function renderProvider() {
  await act(async () => {
    create(
      <FavoritesProvider>
        <FavoritesProbe />
      </FavoritesProvider>,
    );
  });
}

describe("FavoritesProvider", () => {
  beforeEach(() => {
    favoriteState = null;
    storage.getItem.mockReset();
    storage.setItem.mockReset();
    storage.setItem.mockResolvedValue(undefined);
  });

  it("carrega os favoritos persistidos e expõe o estado pronto", async () => {
    storage.getItem.mockResolvedValue('["paulo-de-tarso", "calvino"]');

    await renderProvider();

    expect(storage.getItem).toHaveBeenCalledWith("teologos.favorite-theologians");
    expect(favoriteState?.isReady).toBe(true);
    expect(favoriteState?.favoriteSlugs).toEqual(["paulo-de-tarso", "calvino"]);
    expect(favoriteState?.isFavorite("calvino")).toBe(true);
  });

  it("persiste a alternância e restaura o estado salvo na próxima abertura", async () => {
    storage.getItem.mockResolvedValueOnce('["paulo-de-tarso"]');

    await renderProvider();

    await act(async () => {
      favoriteState?.toggleFavorite("calvino");
    });

    expect(favoriteState?.favoriteSlugs).toEqual(["paulo-de-tarso", "calvino"]);
    expect(storage.setItem).toHaveBeenCalledWith(
      "teologos.favorite-theologians",
      '["paulo-de-tarso","calvino"]',
    );

    storage.getItem.mockResolvedValueOnce('["paulo-de-tarso", "calvino"]');
    await renderProvider();

    expect(favoriteState?.favoriteSlugs).toEqual(["paulo-de-tarso", "calvino"]);
  });
});
