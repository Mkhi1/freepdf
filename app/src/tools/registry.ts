import {
  AlignLeft, BadgeCheck, Combine, Crop, Droplet, EyeOff, GitCompare, Globe, Hash, Highlighter, Image, Images,
  Languages, LayoutGrid, Lock, LockOpen, MonitorPlay, PencilLine, PenLine, Presentation, RotateCw, ScanLine,
  ScanText, Scissors, BookOpen, Sheet, Shrink, Table, TextQuote, FileText, FileType, Wrench,
} from "lucide-preact";
import type { LucideIcon } from "lucide-preact";

export type Category = "organize" | "optimize" | "convert" | "edit" | "security";

export const CATEGORIES: ReadonlyArray<{ id: Category; label: string }> = [
  { id: "organize", label: "Organize" },
  { id: "optimize", label: "Optimize" },
  { id: "convert", label: "Convert" },
  { id: "edit", label: "Edit" },
  { id: "security", label: "Security" },
];

export type ToolId =
  | "reader" | "merge" | "split" | "organize" | "rotate" | "crop"
  | "compress" | "repair" | "pdfa" | "ocr"
  | "word_to_pdf" | "ppt_to_pdf" | "excel_to_pdf" | "images_to_pdf" | "html_to_pdf" | "scan_to_pdf"
  | "pdf_to_word" | "pdf_to_ppt" | "pdf_to_excel" | "pdf_to_images" | "pdf_to_text"
  | "edit" | "sign" | "watermark" | "page_numbers" | "redact" | "annotate" | "compare"
  | "translate" | "summarize" | "protect" | "unlock";

export interface ToolDef {
  id: ToolId;
  name: string;
  blurb: string;
  action: string;
  category: Category;
  icon: LucideIcon;
  /** Lower-case file extensions the tool takes. */
  accepts: readonly string[];
  min: number;
  /** null means no limit. */
  max: number | null;
  /** Options form id (see options/index.ts), or null when a visual editor handles the tool. */
  form: ToolId | null;
  /** Visual editor tools open a placeholder route until their editor is built. */
  editor: boolean;
}

const PDF = ["pdf"] as const;

function pdfTool(
  id: ToolId, name: string, blurb: string, action: string, category: Category, icon: LucideIcon,
  extra: Partial<ToolDef> = {},
): ToolDef {
  return { id, name, blurb, action, category, icon, accepts: PDF, min: 1, max: 1, form: id, editor: false, ...extra };
}

const EDITOR = { form: null, editor: true } as const;

export const TOOLS: readonly ToolDef[] = [
  pdfTool("reader", "Read a PDF", "Read and study with search, highlights and notes.", "Open", "organize", BookOpen, EDITOR),
  pdfTool("merge", "Merge PDFs", "Join several files into one, in the order you choose.", "Merge", "organize", Combine, { min: 2, max: null }),
  pdfTool("split", "Split a PDF", "Cut a file into ranges, single pages or smaller parts.", "Split", "organize", Scissors),
  pdfTool("organize", "Organize pages", "Reorder, delete, rotate and add blank pages.", "Save changes", "organize", LayoutGrid, EDITOR),
  pdfTool("rotate", "Rotate pages", "Turn all pages, or only some, to the right way up.", "Rotate", "organize", RotateCw),

  pdfTool("compress", "Compress a PDF", "Make a heavy file small enough to send.", "Compress", "optimize", Shrink),
  pdfTool("repair", "Repair a PDF", "Rebuild a file that will not open properly.", "Repair", "optimize", Wrench),
  pdfTool("pdfa", "Convert to PDF/A", "Save a long-term archive copy of a document.", "Convert", "optimize", BadgeCheck),
  pdfTool("ocr", "Recognize text", "Make scanned pages searchable and selectable.", "Recognize text", "optimize", ScanText),

  { id: "word_to_pdf", name: "Word to PDF", blurb: "Turn Word documents into PDFs.", action: "Convert", category: "convert", icon: FileText, accepts: ["doc", "docx", "odt", "rtf"], min: 1, max: null, form: "word_to_pdf", editor: false },
  { id: "ppt_to_pdf", name: "PowerPoint to PDF", blurb: "Turn slide decks into PDFs.", action: "Convert", category: "convert", icon: Presentation, accepts: ["ppt", "pptx", "odp"], min: 1, max: null, form: "ppt_to_pdf", editor: false },
  { id: "excel_to_pdf", name: "Excel to PDF", blurb: "Turn spreadsheets into PDFs.", action: "Convert", category: "convert", icon: Sheet, accepts: ["xls", "xlsx", "ods", "csv"], min: 1, max: null, form: "excel_to_pdf", editor: false },
  { id: "images_to_pdf", name: "Images to PDF", blurb: "Put photos and scans on pages of one PDF.", action: "Create PDF", category: "convert", icon: Images, accepts: ["jpg", "jpeg", "png", "bmp", "gif", "tif", "tiff", "webp"], min: 1, max: null, form: "images_to_pdf", editor: false },
  { id: "html_to_pdf", name: "Web page to PDF", blurb: "Save a web address or an HTML file as a PDF.", action: "Convert", category: "convert", icon: Globe, accepts: ["html", "htm"], min: 0, max: 1, form: "html_to_pdf", editor: false },
  { id: "scan_to_pdf", name: "Scan to PDF", blurb: "Scan paper with a connected scanner.", action: "Scan", category: "convert", icon: ScanLine, accepts: [], min: 0, max: 0, form: "scan_to_pdf", editor: false },
  pdfTool("pdf_to_word", "PDF to Word", "Get an editable document from a PDF.", "Convert", "convert", FileType),
  pdfTool("pdf_to_ppt", "PDF to PowerPoint", "Turn pages into editable slides.", "Convert", "convert", MonitorPlay),
  pdfTool("pdf_to_excel", "PDF to Excel", "Pull tables into a spreadsheet.", "Convert", "convert", Table),
  pdfTool("pdf_to_images", "PDF to images", "Save pages, or the pictures inside them, as JPG or PNG.", "Convert", "convert", Image),
  pdfTool("pdf_to_text", "PDF to text", "Copy all the text out into a plain text file.", "Extract text", "convert", AlignLeft),
  pdfTool("translate", "Translate a PDF", "Translate on this computer and keep the layout.", "Translate", "convert", Languages),
  pdfTool("summarize", "Summarize a PDF", "Get the key sentences without leaving the app.", "Summarize", "convert", TextQuote),

  pdfTool("edit", "Edit a PDF", "Add text, images, shapes and drawings.", "Save changes", "edit", PencilLine, EDITOR),
  pdfTool("annotate", "Annotate", "Highlight, underline and leave notes.", "Save changes", "edit", Highlighter, EDITOR),
  pdfTool("watermark", "Add a watermark", "Stamp text or a picture across your pages.", "Add watermark", "edit", Droplet),
  pdfTool("page_numbers", "Number the pages", "Add page numbers in the style you want.", "Add numbers", "edit", Hash),
  pdfTool("crop", "Crop pages", "Trim the margins by drawing a box.", "Crop", "edit", Crop, EDITOR),

  pdfTool("protect", "Protect with a password", "Lock a file so only people with the password can open it.", "Protect", "security", Lock),
  pdfTool("unlock", "Remove a password", "Save a copy that opens without a password.", "Unlock", "security", LockOpen),
  pdfTool("sign", "Sign a PDF", "Place your signature or type a name.", "Save signed copy", "security", PenLine, EDITOR),
  pdfTool("redact", "Redact", "Permanently remove private text and areas.", "Apply redactions", "security", EyeOff, EDITOR),
  pdfTool("compare", "Compare two PDFs", "See what changed between two versions.", "Compare", "security", GitCompare, { ...EDITOR, min: 2, max: 2 }),
];

const BY_ID = new Map<string, ToolDef>(TOOLS.map((t) => [t.id, t]));

export function getTool(id: string): ToolDef | undefined {
  return BY_ID.get(id);
}

/** Where a tool opens once it has its files. */
export function toolRoute(tool: ToolDef): string {
  return `${tool.editor ? "editor" : "work"}/${tool.id}`;
}

/** Tools to suggest after each tool, by id. Falls back to the same category. */
const NEXT: Partial<Record<ToolId, ToolId[]>> = {
  merge: ["compress", "page_numbers", "protect"],
  split: ["merge", "compress", "rotate"],
  compress: ["protect", "merge", "pdf_to_images"],
  repair: ["compress", "ocr", "pdf_to_text"],
  ocr: ["pdf_to_text", "summarize", "translate"],
  rotate: ["page_numbers", "compress", "merge"],
  watermark: ["protect", "compress", "page_numbers"],
  page_numbers: ["watermark", "compress", "protect"],
  protect: ["compress", "merge", "split"],
  unlock: ["compress", "merge", "ocr"],
  summarize: ["translate", "pdf_to_text", "split"],
  translate: ["summarize", "compress", "protect"],
  pdf_to_text: ["summarize", "translate", "ocr"],
};

export function nextTools(id: ToolId): ToolDef[] {
  const listed = NEXT[id];
  const own = getTool(id)?.category;
  const ids = listed ?? TOOLS.filter((t) => t.category === own && t.id !== id).map((t) => t.id).slice(0, 3);
  return ids.map(getTool).filter((t): t is ToolDef => t !== undefined);
}

export function categoryLabel(category: Category): string {
  return CATEGORIES.find((c) => c.id === category)?.label ?? category;
}
