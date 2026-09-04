import AsyncStorage from "@react-native-async-storage/async-storage";

import type { MarketNewsItem } from "@/lib/flowcore";

const NEWS_FAVORITES_KEY = "flowcore.news.favorites.v1";

export type NewsFavorites = Record<string, MarketNewsItem>;

function normalize(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("pt-BR").trim();
}

export function filterNewsItems(items: MarketNewsItem[], query: string) {
  const needle = normalize(query);
  if (!needle) return items;
  return items.filter(item => normalize([
    item.headline,
    item.publisher ?? "",
    item.provider.name,
    item.category,
    item.related_region,
    ...item.section_tags,
    ...item.related_assets,
  ].join(" ")).includes(needle));
}

export async function loadNewsFavorites(): Promise<NewsFavorites> {
  try {
    const saved = await AsyncStorage.getItem(NEWS_FAVORITES_KEY);
    if (!saved) return {};
    const parsed: unknown = JSON.parse(saved);
    if (!Array.isArray(parsed)) return {};
    return Object.fromEntries(parsed.filter((item): item is MarketNewsItem => Boolean(
      item && typeof item === "object" && "id" in item && "headline" in item,
    )).map(item => [item.id, item]));
  } catch {
    return {};
  }
}

export async function persistNewsFavorites(favorites: NewsFavorites) {
  await AsyncStorage.setItem(NEWS_FAVORITES_KEY, JSON.stringify(Object.values(favorites)));
}
