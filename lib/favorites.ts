export const FAVORITE_THEOLOGIANS_STORAGE_KEY = "teologos.favorite-theologians";

function normalizeSlug(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const slug = value.trim();
  return slug.length > 0 ? slug : null;
}

/** Converts untrusted persisted data into a stable, duplicate-free slug list. */
export function normalizeFavoriteSlugs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  const slugs = value
    .map(normalizeSlug)
    .filter((slug): slug is string => slug !== null);

  return [...new Set(slugs)];
}

/** Reads persisted JSON defensively so corrupted local data never blocks the catalog. */
export function parseFavoriteSlugs(raw: string | null): string[] {
  if (!raw) return [];

  try {
    return normalizeFavoriteSlugs(JSON.parse(raw));
  } catch {
    return [];
  }
}

/** Adds or removes one theologian while preserving the original order of saved items. */
export function toggleFavoriteSlug(slugs: string[], slug: string): string[] {
  const normalizedSlug = normalizeSlug(slug);
  const current = normalizeFavoriteSlugs(slugs);

  if (!normalizedSlug) return current;
  if (current.includes(normalizedSlug)) {
    return current.filter((item) => item !== normalizedSlug);
  }

  return [...current, normalizedSlug];
}
