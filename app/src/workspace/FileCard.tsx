import { useState } from "preact/hooks";
import { FileText, Lock, TriangleAlert, X } from "lucide-preact";
import { fileExt, formatBytes } from "../engine/files";
import { inspect, removeFile } from "../state/session";
import type { FileEntry } from "../state/session";
import { FileName } from "../ui/FileName";
import { PageImage } from "../ui/PageImage";

function PasswordPrompt({ file }: { file: FileEntry }) {
  const [text, setText] = useState("");
  const submit = (e: Event) => {
    e.preventDefault();
    if (text) void inspect(file.path, text);
  };
  return (
    <form class="pw" onSubmit={submit}>
      <Lock size={18} aria-hidden="true" />
      <p>This file is locked. Type its password to open it.</p>
      <input class="input" type="password" dir="ltr" value={text} placeholder="Password" onInput={(e) => setText(e.currentTarget.value)} autoFocus />
      {file.error ? <small class="pw-error">{file.error}</small> : null}
      <button type="submit" class="btn small primary" disabled={!text}>Unlock</button>
    </form>
  );
}

export interface FileCardProps {
  file: FileEntry;
  index: number;
  count: number;
  /** Props from useReorder, when the card can be dragged. */
  drag?: Record<string, unknown>;
  dragState?: string;
}

export function FileCard({ file, index, count, drag, dragState }: FileCardProps) {
  const detail = [file.pages ? `${file.pages} ${file.pages === 1 ? "page" : "pages"}` : "", formatBytes(file.bytes)].filter(Boolean).join(" · ");
  return (
    <article class={dragState ? `fcard ri-${dragState}` : "fcard"} tabIndex={drag ? 0 : undefined} aria-label={drag ? `${file.name}, position ${index + 1} of ${count}. Hold Alt and press an arrow key to move.` : undefined} {...drag}>
      <div class="fcard-thumb">
        {file.status === "locked" ? <PasswordPrompt file={file} /> : null}
        {file.status === "error" ? (
          <div class="fcard-problem"><TriangleAlert size={22} /><p>{file.error}</p></div>
        ) : null}
        {file.status === "loading" ? <span class="pageimg-wait" /> : null}
        {file.status === "ready" && file.pdf ? <PageImage file={file.path} page={0} width={220} password={file.password} bare /> : null}
        {file.status === "ready" && !file.pdf ? (
          <div class="fcard-type"><FileText size={34} strokeWidth={1.4} /><b>{fileExt(file.path).toUpperCase()}</b></div>
        ) : null}
        <button type="button" class="icon-btn fcard-remove" aria-label={`Remove ${file.name}`} onClick={() => removeFile(file.path)}>
          <X size={16} />
        </button>
        {count > 1 ? <span class="fcard-order">{index + 1}</span> : null}
      </div>
      <div class="fcard-info">
        <FileName name={file.name} />
        <span class="fcard-detail">{detail}{file.scanned ? " · scanned" : ""}</span>
      </div>
    </article>
  );
}
