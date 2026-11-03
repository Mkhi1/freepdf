// Stand-in engine used only when the UI runs outside Tauri (browser previews, screenshots).
import { EngineFailure } from "./types";
import type { EngineResult, ProgressHandler } from "./types";

export const MOCK_FILES = [
  "C:\\Users\\Student\\Documents\\Biology notes - chapter 4.pdf",
  "C:\\Users\\Student\\Documents\\ملخص الفيزياء.pdf",
  "C:\\Users\\Student\\Downloads\\Lab report draft.pdf",
];

let cancelled = false;
export function mockCancel(): void {
  cancelled = true;
}

export function mockPick(accepts: readonly string[], multiple: boolean): string[] {
  const ext = accepts[0] ?? "pdf";
  if (ext === "png" || ext === "jpg") {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120"><rect width="240" height="120" rx="14" fill="#f59e0b"/><circle cx="70" cy="60" r="34" fill="#fff"/><path d="M120 90l40-50 40 50z" fill="#7c2d12"/></svg>`;
    return [`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`];
  }
  const files = MOCK_FILES.map((p) => p.replace(/\.pdf$/, `.${ext}`));
  return multiple ? files : files.slice(0, 1);
}

/** Page sizes in points. Page 3 is landscape so editors meet mixed sizes. */
export function mockSizes(count = 12): Array<[number, number]> {
  return Array.from({ length: count }, (_, i) => (i === 2 ? [841.89, 595.28] : [595.28, 841.89]));
}

function pageSvg(page: number, width: number): string {
  const [pw, ph] = mockSizes()[page] ?? [595.28, 841.89];
  const h = Math.round((width * ph) / pw);
  const lines = Array.from({ length: 9 }, (_, i) => {
    const w = 40 + ((i * 37 + page * 23) % 50);
    return `<rect x="12%" y="${28 + i * 7}%" width="${w * 0.76}%" height="2.2%" rx="1" fill="#c9d3da"/>`;
  }).join("");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${h}" viewBox="0 0 ${width} ${h}">` +
    `<rect width="100%" height="100%" fill="#fff"/>` +
    `<rect x="12%" y="9%" width="46%" height="5%" rx="2" fill="#0e7490" opacity=".75"/>` +
    `<rect x="12%" y="17%" width="30%" height="2.4%" rx="1" fill="#8aa0ad"/>${lines}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const DOCS = "C:\Users\Student\Documents\Biology notes - chapter 4";

/** Reply shapes follow what the real engine returns for each tool (outputs paths, summary fields). */
function mockReply(tool: string): EngineResult {
  const pdf = (label: string, size = 1_830_000) => ({ path: `${DOCS} (${label}).pdf`, size });
  switch (tool) {
    case "compress":
      return { outputs: [pdf("compressed")], summary: { before: 3_210_000, after: 1_830_000, percent: 43, level: "recommended", unchanged: false, note: "" } };
    case "summarize":
      return {
        outputs: [{ path: `${DOCS} (summary medium).txt`, size: 900 }],
        summary: { text: "Cells are the basic unit of life. Mitochondria produce most of the energy a cell uses.", length: "medium", sentences: 2, total_sentences: 40 },
      };
    case "pdf_to_text":
      return { outputs: [{ path: `${DOCS}.txt`, size: 4200 }], summary: { characters: 4200, pages: 12, has_text: true } };
    case "pdf_to_word":
      return { outputs: [{ path: `${DOCS}.docx`, size: 64_000 }], summary: { engine: "pdf2docx", text_recall: 1 } };
    case "pdf_to_ppt":
      return { outputs: [{ path: `${DOCS}.pptx`, size: 410_000 }], summary: { slides: 12 } };
    case "pdf_to_excel":
      return { outputs: [{ path: `${DOCS}.xlsx`, size: 22_000 }], summary: { sheets: 3, tables: 2 } };
    case "pdf_to_images":
      return { outputs: [{ path: `${DOCS} (images).zip`, size: 900_000 }], summary: { images: 12, mode: "pages" } };
    case "split":
      return { outputs: [{ path: `${DOCS} (split).zip`, size: 1_700_000 }], summary: { parts: 3, zipped: true } };
    case "ocr":
      return { outputs: [pdf("OCR")], summary: { pages_read: 12, pages_skipped: 0, words: 3400 } };
    case "repair":
      return { outputs: [pdf("repaired")], summary: { pages_total: 12, pages_recovered: 12, pages_lost: 0, was_repaired: true } };
    case "protect":
      return { outputs: [pdf("protected")], summary: { encryption: "AES-256", restricted: false } };
    default:
      return { outputs: [pdf(tool)], summary: {} };
  }
}

async function runJob(tool: string, onProgress?: ProgressHandler): Promise<EngineResult> {
  cancelled = false;
  for (let step = 1; step <= 5; step += 1) {
    await sleep(220);
    if (cancelled) throw new EngineFailure("cancelled", "Stopped.");
    onProgress?.({ id: "mock", value: step / 5, message: `Page ${step * 2} of 10` });
  }
  return mockReply(tool);
}

function signatureSvg(text: string, color: string): string {
  const safe = text.replace(/[<&>]/g, "");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="90" viewBox="0 0 320 90">` +
    `<text x="10" y="58" font-family="Segoe Script, cursive" font-size="40" fill="${color}">${safe}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

/** Every call is kept on window so browser checks can read the exact arguments an editor sent. */
function record(tool: string, args: Record<string, unknown>): void {
  const w = window as unknown as { __calls?: Array<{ tool: string; args: Record<string, unknown> }> };
  if (tool !== "info" && tool !== "thumb") (w.__calls ??= []).push({ tool, args: JSON.parse(JSON.stringify(args)) });
}

export async function mockCall(
  tool: string,
  args: Record<string, unknown>,
  onProgress?: ProgressHandler,
): Promise<EngineResult> {
  record(tool, args);
  const staged = await (await import("../editors/mockTools")).mockEditorTool(tool, args);
  if (staged) return staged;
  if (tool === "search") {
    const query = String(args.query ?? "");
    const hits = query ? [
      { page: 0, rects: [[71.4, 76, 330, 98], [71.4, 160, 250, 178]] },
      { page: 1, rects: [[71.4, 220, 300, 238]] },
    ] : [];
    return { outputs: [], summary: { hits, total: hits.reduce((n, h) => n + h.rects.length, 0) } };
  }
  if (tool === "make_signature") {
    const path = signatureSvg(String(args.text ?? ""), String(args.color ?? "#0d1a73"));
    return { outputs: [{ path }], summary: { path, font: "segoesc.ttf" } };
  }
  if (tool === "info") {
    const locked = String(args.file).includes("locked") && !args.password;
    return {
      outputs: [],
      summary: {
        pages: locked ? 0 : 12,
        sizes: locked ? [] : mockSizes(),
        encrypted: locked,
        needs_password: locked,
        scanned: false,
        title: "",
        bytes: 3_210_000,
      },
    };
  }
  if (tool === "thumb") {
    return { outputs: [], summary: { path: pageSvg(Number(args.page ?? 0), Number(args.width ?? 200)) } };
  }
  if (tool === "list_scanners") {
    return { outputs: [], summary: { devices: [{ id: "mock", name: "Sample flatbed scanner" }] } };
  }
  return runJob(tool, onProgress);
}
