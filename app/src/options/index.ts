import type { FormMap, FormSpec } from "./types";

type Loader = () => Promise<{ specs: FormMap }>;

// One chunk per family of tools, loaded the first time a tool in it opens.
const LOADERS: Record<string, Loader> = {
  merge: () => import("./pages"),
  split: () => import("./pages"),
  rotate: () => import("./pages"),
  compress: () => import("./optimize"),
  repair: () => import("./optimize"),
  pdfa: () => import("./optimize"),
  ocr: () => import("./optimize"),
  word_to_pdf: () => import("./intopdf"),
  ppt_to_pdf: () => import("./intopdf"),
  excel_to_pdf: () => import("./intopdf"),
  images_to_pdf: () => import("./intopdf"),
  html_to_pdf: () => import("./intopdf"),
  scan_to_pdf: () => import("./intopdf"),
  pdf_to_word: () => import("./outofpdf"),
  pdf_to_ppt: () => import("./outofpdf"),
  pdf_to_excel: () => import("./outofpdf"),
  pdf_to_images: () => import("./outofpdf"),
  pdf_to_text: () => import("./outofpdf"),
  watermark: () => import("./mark"),
  page_numbers: () => import("./mark"),
  translate: () => import("./textual"),
  summarize: () => import("./textual"),
  protect: () => import("./textual"),
  unlock: () => import("./textual"),
};

export async function loadForm(id: string): Promise<FormSpec> {
  const load = LOADERS[id];
  if (!load) throw new Error(`No options form for ${id}`);
  const module = await load();
  const spec = module.specs[id];
  if (!spec) throw new Error(`Options form missing for ${id}`);
  return spec;
}
