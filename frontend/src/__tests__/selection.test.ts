import { describe, expect, it } from "vitest";
import { canCompare, parseIds, toggleSelection } from "../lib/selection";

describe("sélection de comparaison", () => {
  it("n'autorise la comparaison qu'entre 2 et 5 composants", () => {
    expect(canCompare([1])).toBe(false);
    expect(canCompare([1, 2])).toBe(true);
    expect(canCompare([1, 2, 3, 4, 5])).toBe(true);
    expect(canCompare([1, 2, 3, 4, 5, 6])).toBe(false);
  });

  it("bloque le 6e composant et signale la limite", () => {
    let ids: number[] = [];
    for (const id of [1, 2, 3, 4, 5]) ids = toggleSelection(ids, id).ids;
    const res = toggleSelection(ids, 6);
    expect(res.limited).toBe(true);
    expect(res.ids).toEqual([1, 2, 3, 4, 5]);
    expect(toggleSelection(res.ids, 3).ids).toEqual([1, 2, 4, 5]);
  });

  it("lit les ids d'URL en ignorant doublons et valeurs invalides", () => {
    expect(parseIds("3,3,abc,7,0,1,2,4,9")).toEqual([3, 7, 1, 2, 4]);
    expect(parseIds(null)).toEqual([]);
  });
});
