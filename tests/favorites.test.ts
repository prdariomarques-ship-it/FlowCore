import { describe, expect, it } from "vitest";

import { normalizeFavoriteSlugs, parseFavoriteSlugs, toggleFavoriteSlug } from "../lib/favorites";

describe("favoritos locais", () => {
  it("normaliza, remove valores inválidos e preserva a ordem dos slugs únicos", () => {
    expect(normalizeFavoriteSlugs(["agostinho", " agostinho ", "calvino", "", 7, null])).toEqual([
      "agostinho",
      "calvino",
    ]);
  });

  it("tolera dados persistidos inválidos sem bloquear o catálogo", () => {
    expect(parseFavoriteSlugs("not-json")).toEqual([]);
    expect(parseFavoriteSlugs('["origenes", "origenes", ""]')).toEqual(["origenes"]);
  });

  it("alterna um teólogo sem duplicar e depois o remove", () => {
    const saved = toggleFavoriteSlug(["agostinho"], "calvino");
    expect(saved).toEqual(["agostinho", "calvino"]);
    expect(toggleFavoriteSlug(saved, "agostinho")).toEqual(["calvino"]);
  });
});
