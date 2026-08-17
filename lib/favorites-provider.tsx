import React, { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  toggleFavoriteSlug,
} from "./favorites";
import { loadFavoriteSlugs, saveFavoriteSlugs } from "./favorites-storage";

type FavoritesContextValue = {
  favoriteSlugs: string[];
  favoriteCount: number;
  isReady: boolean;
  isFavorite: (slug: string) => boolean;
  toggleFavorite: (slug: string) => void;
};

const FavoritesContext = createContext<FavoritesContextValue | null>(null);

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const [favoriteSlugs, setFavoriteSlugs] = useState<string[]>([]);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let active = true;

    void loadFavoriteSlugs()
      .then((stored) => {
        if (active) setFavoriteSlugs(stored);
      })
      .catch(() => {
        if (active) setFavoriteSlugs([]);
      })
      .finally(() => {
        if (active) setIsReady(true);
      });

    return () => {
      active = false;
    };
  }, []);

  const toggleFavorite = useCallback(
    (slug: string) => {
      if (!isReady) return;

      setFavoriteSlugs((current) => {
        const next = toggleFavoriteSlug(current, slug);
        void saveFavoriteSlugs(next).catch(() => undefined);
        return next;
      });
    },
    [isReady],
  );

  const favoriteSet = useMemo(() => new Set(favoriteSlugs), [favoriteSlugs]);
  const value = useMemo<FavoritesContextValue>(
    () => ({
      favoriteSlugs,
      favoriteCount: favoriteSlugs.length,
      isReady,
      isFavorite: (slug) => favoriteSet.has(slug),
      toggleFavorite,
    }),
    [favoriteSet, favoriteSlugs, isReady, toggleFavorite],
  );

  return <FavoritesContext.Provider value={value}>{children}</FavoritesContext.Provider>;
}

export function useFavorites(): FavoritesContextValue {
  const value = useContext(FavoritesContext);
  if (!value) throw new Error("useFavorites deve ser usado dentro de FavoritesProvider.");
  return value;
}
