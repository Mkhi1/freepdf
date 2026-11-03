export interface Marked { text: string; rect: [number, number, number, number] }

export interface PagePair {
  page: number;
  page_a: number | null;
  page_b: number | null;
  added?: Marked[];
  removed?: Marked[];
  image?: string;
  difference_percent?: number;
  regions?: number[][];
  changed: boolean;
  size_changed?: boolean;
}

export interface Change {
  /** Row in the pair list. */
  row: number;
  kind: "added" | "removed" | "visual";
  text: string;
  rect?: [number, number, number, number];
  key: string;
}

/** Flat, in-reading-order list of everything that differs, for the side list. */
export function listChanges(pairs: readonly PagePair[], mode: "text" | "visual"): Change[] {
  const out: Change[] = [];
  pairs.forEach((pair, row) => {
    if (mode === "visual") {
      if (pair.changed) {
        const pct = pair.difference_percent ?? 0;
        out.push({ row, kind: "visual", text: `${pct < 0.1 ? "<0.1" : pct.toFixed(1)}% of the page differs`, key: `v${row}` });
      }
      return;
    }
    const mix = [
      ...(pair.removed ?? []).map((m, i) => ({ m, kind: "removed" as const, key: `r${row}-${i}` })),
      ...(pair.added ?? []).map((m, i) => ({ m, kind: "added" as const, key: `a${row}-${i}` })),
    ].sort((x, y) => x.m.rect[1] - y.m.rect[1] || x.m.rect[0] - y.m.rect[0]);
    mix.forEach(({ m, kind, key }) => out.push({ row, kind, text: m.text, rect: m.rect, key }));
  });
  return out;
}

export function pageLabel(pair: PagePair): string {
  const a = pair.page_a === null ? "-" : pair.page_a + 1;
  const b = pair.page_b === null ? "-" : pair.page_b + 1;
  return a === b ? `Page ${a}` : `Old ${a}, new ${b}`;
}
