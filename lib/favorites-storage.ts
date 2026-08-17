import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  FAVORITE_THEOLOGIANS_STORAGE_KEY,
  normalizeFavoriteSlugs,
  parseFavoriteSlugs,
} from "./favorites";

export type FavoriteStorage = Pick<typeof AsyncStorage, "getItem" | "setItem">;

export async function loadFavoriteSlugs(storage: FavoriteStorage = AsyncStorage): Promise<string[]> {
  try {
    return parseFavoriteSlugs(await storage.getItem(FAVORITE_THEOLOGIANS_STORAGE_KEY));
  } catch {
    return [];
  }
}

export async function saveFavoriteSlugs(
  slugs: string[],
  storage: FavoriteStorage = AsyncStorage,
): Promise<void> {
  const normalized = normalizeFavoriteSlugs(slugs);
  await storage.setItem(FAVORITE_THEOLOGIANS_STORAGE_KEY, JSON.stringify(normalized));
}
