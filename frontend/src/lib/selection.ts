export const COMPARE_MIN = 2;
export const COMPARE_MAX = 5;

/** Toggle an id in a comparison selection, never exceeding COMPARE_MAX. */
export function toggleSelection(ids: number[], id: number, max = COMPARE_MAX): { ids: number[]; limited: boolean } {
  if (ids.includes(id)) return { ids: ids.filter((v) => v !== id), limited: false };
  if (ids.length >= max) return { ids, limited: true };
  return { ids: [...ids, id], limited: false };
}

export function canCompare(ids: number[]): boolean {
  return ids.length >= COMPARE_MIN && ids.length <= COMPARE_MAX;
}

export function parseIds(value: string | null): number[] {
  if (!value) return [];
  const out: number[] = [];
  for (const part of value.split(",")) {
    const n = Number(part);
    if (Number.isInteger(n) && n > 0 && !out.includes(n)) out.push(n);
  }
  return out.slice(0, COMPARE_MAX);
}
