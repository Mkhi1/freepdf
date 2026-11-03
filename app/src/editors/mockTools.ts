// Stand-in results for the organize, compare and reader screens when the UI runs outside Tauri.
import type { EngineResult } from "../engine/types";

function diffSvg(page: number): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="566" viewBox="0 0 400 566">` +
    `<rect width="400" height="566" fill="#fff"/>` +
    [0, 1, 2, 3, 4, 5, 6].map((i) => `<rect x="48" y="${150 + i * 40}" width="${220 + ((i * 41) % 90)}" height="8" fill="#e3e8ec"/>`).join("") +
    `<rect x="48" y="62" width="180" height="22" fill="#e3e8ec"/>` +
    `<rect x="44" y="${190 + page * 6}" width="250" height="16" fill="#dc1e1e" opacity=".8"/>` +
    `<rect x="44" y="340" width="190" height="16" fill="#14a03c" opacity=".8"/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const TEXT_PAGES = [
  {
    page: 0, page_a: 0, page_b: 0, changed: true,
    removed: [{ text: "Mitochondria produce most of the energy", rect: [72, 150, 360, 168] }],
    added: [
      { text: "Mitochondria generate most of the ATP", rect: [72, 150, 340, 168] },
      { text: "ملخص الفيزياء الفصل الرابع", rect: [72, 300, 300, 322] },
    ],
  },
  { page: 1, page_a: 1, page_b: 1, changed: false, removed: [], added: [] },
  {
    page: 2, page_a: null, page_b: 2, changed: true, removed: [],
    added: [{ text: "A whole new page about enzymes", rect: [72, 120, 420, 140] }],
  },
  {
    page: 3, page_a: 2, page_b: 3, changed: true,
    removed: [{ text: "Figure 2 is shown below", rect: [72, 420, 280, 436] }], added: [],
  },
];

function comparePages(mode: string) {
  if (mode === "text") return TEXT_PAGES;
  return TEXT_PAGES.map((p) => ({
    page: p.page, page_a: p.page_a, page_b: p.page_b, image: diffSvg(p.page),
    difference_percent: p.changed ? 1.4 + p.page : 0, regions: [], changed: p.changed, size_changed: false,
  }));
}

/** Handles only the tools these screens need. Returns null for everything else. */
export async function mockEditorTool(tool: string, args: Record<string, unknown>): Promise<EngineResult | null> {
  if (tool === "compare") {
    const mode = String(args.mode ?? "text");
    const dir = "C:\\Users\\Student\\Documents\\";
    return {
      outputs: [{ path: `${dir}Biology notes - chapter 4 (comparison).pdf`, size: 88_000 }],
      summary: { mode, pages: comparePages(mode), pages_a: 3, pages_b: 4, changed_pages: 3, note: "" },
    };
  }
  if (tool === "organize") {
    const count = Array.isArray(args.pages) ? args.pages.length : 0;
    return {
      outputs: [{ path: "C:\\Users\\Student\\Documents\\Biology notes - chapter 4 (organized).pdf", size: 2_100_000 }],
      summary: { pages: count },
    };
  }
  if (tool === "annotate") {
    const count = Array.isArray(args.items) ? args.items.length : 0;
    return {
      outputs: [{ path: "C:\\Users\\Student\\Documents\\Biology notes - chapter 4 (annotated).pdf", size: 3_220_000 }],
      summary: { annotations: count },
    };
  }
  return null;
}
