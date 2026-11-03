import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ChevronDown, ChevronUp, ExternalLink, FolderOpen, Info } from "lucide-preact";
import { FileName, fileName, openFile, showInFolder } from "../kit";
import type { EngineResult } from "../kit";
import { layoutRows, useVisibleRows } from "../reader/virtual";
import { listChanges } from "./changes";
import type { Change, PagePair } from "./changes";
import { PairRow, rowHeight } from "./Rows";
import type { RowCtx, Sizes } from "./Rows";

export interface ResultInput {
  result: EngineResult;
  mode: "text" | "visual";
  fileA: string;
  fileB: string;
  passwordA?: string;
  passwordB?: string;
  sizesA: Sizes;
  sizesB: Sizes;
}

const GAP = 14;

function ChangeList({ changes, active, onPick }: { changes: Change[]; active: Change | null; onPick: (c: Change) => void }) {
  if (!changes.length) return <p class="hint cmp-none">No differences found. The two files match.</p>;
  return (
    <ol class="cmp-changes" aria-label="Changes">
      {changes.map((c) => (
        <li>
          <button type="button" class={`cmp-change ${c.kind}${active?.key === c.key ? " on" : ""}`} onClick={() => onPick(c)}>
            <span class="cmp-dot" aria-hidden="true" />
            <span class="cmp-ctext" dir="auto">{c.text}</span>
            <small>{`Page ${c.row + 1}`}</small>
          </button>
        </li>
      ))}
    </ol>
  );
}

export function Results({ input }: { input: ResultInput }) {
  const { result, mode } = input;
  const pairs = (result.summary.pages ?? []) as PagePair[];
  const report = result.outputs[0];
  const changes = useMemo(() => listChanges(pairs, mode), [result, mode]);
  const [active, setActive] = useState<Change | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const watch = new ResizeObserver(() => setWidth(el.clientWidth));
    watch.observe(el);
    setWidth(el.clientWidth);
    return () => watch.disconnect();
  }, []);

  const columns = mode === "text" ? 2 : 1;
  const colWidth = Math.max(220, Math.min(760, Math.floor((width - 56 - (columns - 1) * 18) / columns)));
  const ctx: RowCtx = { ...input, colWidth, active };
  const heights = useMemo(() => pairs.map((p) => rowHeight(p, ctx)), [result, colWidth, mode]);
  const layout = useMemo(() => layoutRows(heights, GAP, 12), [heights]);
  const vis = useVisibleRows(box, layout, heights);

  const jump = (index: number) => {
    const next = changes[(index + changes.length) % changes.length];
    if (!next) return;
    setActive(next);
    const rect = next.rect;
    const size = input.sizesB[pairs[next.row].page_b ?? 0] ?? input.sizesA[pairs[next.row].page_a ?? 0] ?? [595, 842];
    const inside = rect ? (rect[1] / size[1]) * (heights[next.row] - 30) : 0;
    box.current?.scrollTo({ top: Math.max(0, layout.tops[next.row] + inside - 120), behavior: "smooth" });
  };
  const at = active ? changes.findIndex((c) => c.key === active.key) : -1;
  const onKey = (e: KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName === "INPUT") return;
    if (e.key === "p" || (e.key === "F3" && e.shiftKey)) { e.preventDefault(); jump(at - 1); }
    else if (e.key === "n" || e.key === "F3") { e.preventDefault(); jump(at + 1); }
  };

  const summary = result.summary;
  const changedPages = pairs.filter((p) => p.changed).length;
  return (
    <div class="cmp-result" onKeyDown={onKey}>
      <aside class="cmp-side" aria-label="Changes">
        <div class="cmp-side-head">
          <h2>{changes.length ? `${changes.length} ${changes.length === 1 ? "change" : "changes"}` : "No changes"}</h2>
          <p class="hint">{changedPages} of {pairs.length} pages differ.</p>
          <div class="btn-row">
            <button type="button" class="btn small" disabled={!changes.length} onClick={() => jump(at - 1)}><ChevronUp size={15} /> Previous</button>
            <button type="button" class="btn small" disabled={!changes.length} onClick={() => jump(at + 1)}><ChevronDown size={15} /> Next</button>
          </div>
          <div class="cmp-legend">
            <span><i class="cmp-dot removed" /> {mode === "text" ? "Only in the old file" : "Only in the old file (red)"}</span>
            <span><i class="cmp-dot added" /> {mode === "text" ? "Only in the new file" : "Only in the new file (green)"}</span>
          </div>
        </div>
        <ChangeList changes={changes} active={active} onPick={(c) => jump(changes.indexOf(c))} />
        {report ? (
          <div class="cmp-report">
            <b>PDF report</b>
            <FileName name={fileName(report.path)} />
            <div class="btn-row">
              <button type="button" class="btn small primary" onClick={() => void openFile(report.path)}><ExternalLink size={14} /> Open</button>
              <button type="button" class="btn small" onClick={() => void showInFolder(report.path)}><FolderOpen size={14} /> Show in folder</button>
            </div>
          </div>
        ) : null}
      </aside>
      <div class="cmp-main">
        {summary.note ? <p class="notice cmp-note"><Info size={15} /> {String(summary.note)}</p> : null}
        <div class="cmp-heads" style={{ paddingInline: "28px" }}>
          <span><b>Old</b> <FileName name={fileName(input.fileA)} /></span>
          <span><b>New</b> <FileName name={fileName(input.fileB)} /></span>
        </div>
        <div class="cmp-scroll" ref={box} tabIndex={0}>
          <div style={{ height: `${layout.total}px`, position: "relative" }}>
            {pairs.slice(vis.first, vis.last + 1).map((pair, i) => {
              const row = vis.first + i;
              return (
                <div key={row} class="cmp-slot" style={{ top: `${layout.tops[row]}px`, height: `${heights[row]}px` }}>
                  <PairRow pair={pair} row={row} ctx={ctx} />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
