import { useState } from "preact/hooks";
import { Plus, ScanLine } from "lucide-preact";
import { formatBytes } from "../engine/files";
import { FileName } from "../ui/FileName";
import { PageImage } from "../ui/PageImage";
import type { FileEntry } from "../state/session";
import type { ToolDef } from "../tools/registry";
import { slotToIndex, useReorder } from "../ui/useReorder";
import { FileCard } from "./FileCard";

const PAGE_STEP = 48;

function PageGrid({ file }: { file: FileEntry }) {
  const [shown, setShown] = useState(PAGE_STEP);
  const total = file.pages ?? 0;
  const count = Math.min(total, shown);
  return (
    <>
      <div class="pages-grid">
        {Array.from({ length: count }, (_, page) => (
          <figure class="pg">
            <PageImage file={file.path} page={page} width={200} password={file.password} />
            <figcaption>{page + 1}</figcaption>
          </figure>
        ))}
      </div>
      {total > count ? (
        <button type="button" class="btn" onClick={() => setShown(shown + PAGE_STEP)}>Show more pages ({total - count} left)</button>
      ) : null}
    </>
  );
}

function SingleFile({ file, tool }: { file: FileEntry; tool: ToolDef }) {
  const ready = file.status === "ready" && file.pdf && file.pages;
  return (
    <div class="single">
      <div class="single-head">
        <FileName name={file.name} class="single-name" />
        <span class="single-meta">
          {file.pages ? `${file.pages} ${file.pages === 1 ? "page" : "pages"}` : ""}
          {file.bytes ? ` · ${formatBytes(file.bytes)}` : ""}
          {file.scanned ? " · looks scanned" : ""}
        </span>
      </div>
      {ready ? <PageGrid file={file} /> : <FileCard file={file} index={0} count={1} />}
      {file.scanned && ["pdf_to_text", "pdf_to_word", "summarize", "translate"].includes(tool.id) ? (
        <p class="tip">This looks like a scan. Run "Recognize text" first so there is text to work with.</p>
      ) : null}
    </div>
  );
}

export interface StageProps {
  tool: ToolDef;
  files: readonly FileEntry[];
  canAdd: boolean;
  onAdd: () => void;
  onMove: (from: number, to: number) => void;
}

export function Stage({ tool, files, canAdd, onAdd, onMove }: StageProps) {
  const reorder = useReorder({ onReorder: (from, slot) => onMove(from, slotToIndex(from, slot)) });
  if (tool.max === 0) {
    return (
      <div class="stage-empty">
        <ScanLine size={44} strokeWidth={1.3} />
        <h2>Ready to scan</h2>
        <p>Put the page face down on the scanner, choose your settings on the right, then press Scan.</p>
      </div>
    );
  }
  if (files.length === 0) {
    return (
      <div class="stage-empty">
        <h2>Nothing to preview</h2>
        <p>Set the options on the right, then press the button below.</p>
      </div>
    );
  }
  if (files.length === 1 && tool.max === 1) return <SingleFile file={files[0]} tool={tool} />;
  return (
    <>
    {files.length > 1 ? <p class="hint reorder-hint">Drag a file to change the order. With the keyboard, focus a file and press Alt with an arrow key.</p> : null}
    <div class="fgrid">
      {files.map((file, index) => (
        <FileCard
          key={file.path}
          file={file}
          index={index}
          count={files.length}
          drag={files.length > 1 ? reorder.itemProps(index) : undefined}
          dragState={reorder.stateOf(index, files.length)}
        />
      ))}
      {canAdd ? (
        <button type="button" class="fadd" onClick={onAdd}>
          <Plus size={26} />
          <span>Add more files</span>
        </button>
      ) : null}
    </div>
    </>
  );
}
