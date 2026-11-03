import { formatBytes } from "../engine/files";

export interface Fact {
  /** Shown in bold before the rest. */
  lead?: string;
  text: string;
}

type Summary = Record<string, unknown>;

const num = (value: unknown): number | null => (typeof value === "number" ? value : null);

function compressFact(s: Summary): Fact | null {
  const before = num(s.before);
  const after = num(s.after);
  if (before === null || after === null) return null;
  const percent = Math.round(num(s.percent) ?? 0);
  const lead = s.unchanged === true || percent <= 0 ? "Already as small as it can get. " : `${percent}% smaller. `;
  return { lead, text: `${formatBytes(before)} down to ${formatBytes(after)}.` };
}

function repairFact(s: Summary): Fact | null {
  const lost = num(s.pages_lost);
  if (!lost) return null;
  return { lead: `${lost} ${lost === 1 ? "page" : "pages"} could not be recovered. `, text: "The rest were saved." };
}

function ocrFact(s: Summary): Fact | null {
  if (num(s.pages_read) === 0) {
    return { lead: "Nothing needed recognising. ", text: "Those pages already have selectable text." };
  }
  return null;
}

function pptFact(s: Summary): Fact | null {
  const kept = num(s.picture_slides);
  if (!kept) return null;
  return {
    lead: `${kept} ${kept === 1 ? "slide stayed a picture" : "slides stayed pictures"}. `,
    text: "They could not be rebuilt as text without damaging them, so they match the PDF exactly but cannot be edited.",
  };
}

function splitFact(s: Summary): Fact | null {
  const over = num(s.pages_over_limit);
  if (!over) return null;
  return { lead: "Some parts are over the limit. ", text: "A single page can be bigger than the size you chose." };
}

function textFact(s: Summary): Fact | null {
  if (s.has_text !== false) return null;
  return { lead: "No text found. ", text: "This looks like a scan. Run Recognize text first, then try again." };
}

const FACTS: Record<string, (s: Summary) => Fact | null> = {
  compress: compressFact,
  repair: repairFact,
  ocr: ocrFact,
  pdf_to_ppt: pptFact,
  split: splitFact,
  pdf_to_text: textFact,
};

export function factFor(toolId: string, summary: Summary): Fact | null {
  return FACTS[toolId]?.(summary) ?? null;
}
