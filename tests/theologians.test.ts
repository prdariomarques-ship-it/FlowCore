import { describe, expect, it } from "vitest";
import { getAllTheologians, getPeriod, periods } from "../data/theologians";

describe("theologian catalog", () => {
  it("contains all nine historical periods with three theologians each", () => {
    expect(periods).toHaveLength(9);
    expect(periods.every((period) => period.theologians.length >= 3)).toBe(true);
    expect(getAllTheologians()).toHaveLength(27);
  });

  it("returns a period and preserves contextual system prompts", () => {
    const reformation = getPeriod("reforma");
    expect(reformation?.title).toBe("Reforma");
    expect(reformation?.theologians.map((item) => item.name)).toEqual([
      "Martinho Lutero",
      "João Calvino",
      "Ulrico Zuínglio",
    ]);
    expect(reformation?.theologians.every((item) => item.prompt.includes("CONTEXTO HISTÓRICO"))).toBe(true);
    expect(reformation?.theologians.every((item) => item.prompt.includes("DIRETRIZES DE RESPOSTA"))).toBe(true);
  });
});
