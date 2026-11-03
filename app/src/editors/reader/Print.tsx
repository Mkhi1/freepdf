import { useEffect, useState } from "preact/hooks";
import { createPortal } from "preact/compat";
import { Loader, Printer, X } from "lucide-preact";
import { loadPage } from "./loader";
import type { Annot } from "./annots";
import { Shapes } from "./Shapes";
import type { Size } from "./Shapes";

const PRINT_WIDTH = 1500;

/** Turns "1-3, 7" into 0-based pages, or null when the text is not a valid range. */
export function parsePages(text: string, count: number): number[] | null {
  const pages = new Set<number>();
  for (const part of text.split(",").map((s) => s.trim()).filter(Boolean)) {
    const m = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(part);
    if (!m) return null;
    const a = Number(m[1]);
    const b = m[2] ? Number(m[2]) : a;
    if (a < 1 || b < a || b > count) return null;
    for (let i = a; i <= b; i += 1) pages.add(i - 1);
  }
  return pages.size ? [...pages].sort((x, y) => x - y) : null;
}

export interface PrintDialogProps {
  count: number;
  current: number;
  onClose: () => void;
  onPrint: (pages: number[]) => void;
}

export function PrintDialog({ count, current, onClose, onPrint }: PrintDialogProps) {
  const [which, setWhich] = useState<"all" | "this" | "range">("all");
  const [range, setRange] = useState("");
  const pages = which === "all" ? Array.from({ length: count }, (_, i) => i)
    : which === "this" ? [current] : parsePages(range, count);
  return (
    <div class="rd-pop rd-print" role="dialog" aria-label="Print">
      <b>Print</b>
      {([["all", `All ${count} pages`], ["this", `This page (${current + 1})`], ["range", "Pages"]] as const).map(([id, label]) => (
        <label class="rd-radio">
          <input type="radio" name="print-which" checked={which === id} onChange={() => setWhich(id)} /> {label}
          {id === "range" ? (
            <input class="input" dir="ltr" placeholder="1-3, 7" value={range} onFocus={() => setWhich("range")}
              onInput={(e) => setRange(e.currentTarget.value)} />
          ) : null}
        </label>
      ))}
      {which === "range" && !pages ? <small class="rd-bad">Use page numbers like 1-3, 7. This file has {count} pages.</small> : null}
      <div class="rd-notepop-row">
        <button type="button" class="btn small" onClick={onClose}>Cancel</button>
        <button type="button" class="btn small primary" disabled={!pages} onClick={() => pages && onPrint(pages)}><Printer size={14} /> Print</button>
      </div>
    </div>
  );
}

export interface PrintJob {
  file: string;
  password?: string;
  pages: number[];
  sizes: readonly Size[];
  annots: readonly Annot[];
}

/** Draws the chosen pages into a print-only layer, then opens the print dialog. */
export function PrintSheet({ job, onDone }: { job: PrintJob; onDone: () => void }) {
  const [images, setImages] = useState<Array<string | null>>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const loaded: Array<string | null> = [];
      for (const page of job.pages) {
        const url = await loadPage({ file: job.file, page, width: PRINT_WIDTH, password: job.password, priority: () => 0, wanted: () => alive });
        if (!alive) return;
        loaded.push(url);
        setImages([...loaded]);
      }
      setReady(true);
    })();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const finish = () => { window.removeEventListener("afterprint", finish); onDone(); };
    window.addEventListener("afterprint", finish);
    const timer = window.setTimeout(() => window.print(), 250);
    return () => { window.clearTimeout(timer); window.removeEventListener("afterprint", finish); };
  }, [ready]);

  const sheet = (
    <div class="printsheet" aria-hidden="true">
      {images.map((src, i) => {
        const page = job.pages[i];
        const size = job.sizes[page] ?? [595, 842];
        return (
          <div class="printpage" key={page} style={{ aspectRatio: `${size[0]} / ${size[1]}` }}>
            {src ? <img src={src} alt="" /> : null}
            <Shapes annots={job.annots.filter((a) => a.page === page)} size={size as Size} />
          </div>
        );
      })}
    </div>
  );
  return (
    <>
      {createPortal(sheet, document.body)}
      <div class="rd-pop rd-printing" role="status">
        <Loader size={16} class="spin" /> {ready ? "Opening the print window" : `Preparing page ${images.length + 1} of ${job.pages.length}`}
        <button type="button" class="btn small" onClick={onDone}><X size={14} /> Cancel</button>
      </div>
    </>
  );
}
