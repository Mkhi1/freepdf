import type { Slot } from "../../ui/useReorder";

export interface PageItem {
  id: number;
  source: string;
  page: number;
  /** Extra clockwise turn in degrees: 0, 90, 180 or 270. */
  rotate: number;
  blank: boolean;
}

export interface Source {
  path: string;
  name: string;
  pages: number;
  sizes: Array<[number, number]>;
}

let nextId = 1;
export const newId = (): number => nextId++;

export function pagesOf(source: Source): PageItem[] {
  return Array.from({ length: source.pages }, (_, page) => ({ id: newId(), source: source.path, page, rotate: 0, blank: false }));
}

export function turn(items: readonly PageItem[], ids: ReadonlySet<number>, degrees: number): PageItem[] {
  return items.map((p) => (ids.has(p.id) ? { ...p, rotate: (((p.rotate + degrees) % 360) + 360) % 360 } : p));
}

export function remove(items: readonly PageItem[], ids: ReadonlySet<number>): PageItem[] {
  return items.filter((p) => !ids.has(p.id));
}

/** Adds a blank page after the last selected page, or at the end when nothing is selected. */
export function addBlank(items: readonly PageItem[], ids: ReadonlySet<number>): PageItem[] {
  let at = items.length;
  items.forEach((p, i) => { if (ids.has(p.id)) at = i + 1; });
  const blank: PageItem = { id: newId(), source: "", page: 0, rotate: 0, blank: true };
  return [...items.slice(0, at), blank, ...items.slice(at)];
}

/** Moves the dragged page, or every selected page when the dragged one is selected, to a slot. */
export function moveMany(items: readonly PageItem[], from: number, slot: Slot, ids: ReadonlySet<number>): PageItem[] {
  const grabbed = items[from];
  const moving = ids.has(grabbed.id) ? items.filter((p) => ids.has(p.id)) : [grabbed];
  const movingIds = new Set(moving.map((p) => p.id));
  const before = items.slice(0, slot).filter((p) => !movingIds.has(p.id)).length;
  const rest = items.filter((p) => !movingIds.has(p.id));
  return [...rest.slice(0, before), ...moving, ...rest.slice(before)];
}

export function selectRange(items: readonly PageItem[], a: number, b: number): Set<number> {
  const [lo, hi] = a < b ? [a, b] : [b, a];
  return new Set(items.slice(lo, hi + 1).map((p) => p.id));
}

export function toArgs(file: string, items: readonly PageItem[], password?: string): Record<string, unknown> {
  return {
    file,
    pages: items.map((p) => (p.blank
      ? { blank: true, rotate: p.rotate }
      : { source: p.source, page: p.page, rotate: p.rotate })),
    ...(password ? { password } : {}),
  };
}
