import { describe, expect, it } from "vitest";
import { getAllTheologians, getPeriod, periods } from "../data/theologians";

describe("theologian catalog", () => {
  it("contains the expanded historical catalog", () => {
    expect(periods).toHaveLength(12);
    expect(periods.every((period) => period.theologians.length >= 3)).toBe(true);
    expect(getAllTheologians()).toHaveLength(93);
    expect(getPeriod("periodo-apostolico")?.theologians.some((item) => item.name === "Paulo de Tarso")).toBe(true);
    expect(getPeriod("neo-ortodoxia")?.theologians.some((item) => item.name === "Karl Barth")).toBe(true);
  });

  it("returns a period and preserves contextual system prompts", () => {
    const reformation = getPeriod("reforma");
    expect(reformation?.title).toBe("Reforma");
    const reformerNames = reformation?.theologians.map((item) => item.name) ?? [];
    expect(reformerNames).toEqual(expect.arrayContaining([
      "Martinho Lutero",
      "João Calvino",
      "Ulrico Zuínglio",
    ]));
    expect(reformation?.theologians.every((item) => item.prompt.includes("CONTEXTO HISTÓRICO"))).toBe(true);
    expect(reformation?.theologians.every((item) => item.prompt.includes("DIRETRIZES DE RESPOSTA"))).toBe(true);
  });
});
