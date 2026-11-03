import { ArrowDownToLine, ArrowUpFromLine, BookOpen, ExternalLink, FolderOpen, TriangleAlert, X } from "lucide-preact";
import { fileName, formatBytes, isPdf, openFile, showInFolder } from "../engine/files";
import { go } from "../state/router";
import { setFiles } from "../state/session";
import { FileName } from "../ui/FileName";
import { cancel, forgetTransfer, formatSpeed } from "./client";
import type { Transfer } from "./types";

function readHere(path: string): void {
  setFiles([path]);
  go("editor/reader");
}

/** Files that run code when opened. They come from another PC, so only "Show in folder" is offered. */
const RUNNABLE = /\.(exe|com|bat|cmd|scr|pif|msi|msp|lnk|url|ps1|psm1|vbs|vbe|js|jse|wsf|wsh|hta|cpl|jar|reg|scf|appref-ms|docm|xlsm|pptm)$/i;

function title(t: Transfer): string {
  const count = t.paths.length;
  if (t.status === "done" && count === 1) return fileName(t.paths[0]);
  if (t.status === "done" && count > 1) return `${count} files`;
  return t.file || (t.direction === "send" ? "Getting ready to send" : "Getting ready to receive");
}

function meta(t: Transfer): string {
  const who = t.direction === "send" ? `To ${t.peerName}` : `From ${t.peerName}`;
  if (t.status === "done") return `${who} · ${t.direction === "send" ? "Sent" : "Received"}${t.total ? ` · ${formatBytes(t.total)}` : ""}`;
  if (t.status === "failed") return who;
  const speed = formatSpeed(t.bytesPerSec);
  const amount = t.total ? `${formatBytes(t.done)} of ${formatBytes(t.total)}` : "Waiting for the other device";
  return [who, amount, speed].filter(Boolean).join(" · ");
}

function Actions({ t }: { t: Transfer }) {
  if (t.status === "running") {
    return <button type="button" class="btn small" onClick={() => void cancel(t.id)}><X size={14} /> Cancel</button>;
  }
  const first = t.paths[0];
  const received = t.status === "done" && t.direction === "receive" && first;
  return (
    <>
      {received && isPdf(first) ? <button type="button" class="btn small" onClick={() => readHere(first)}><BookOpen size={14} /> Open</button> : null}
      {received && !isPdf(first) && !RUNNABLE.test(first) ? <button type="button" class="btn small" onClick={() => void openFile(first)}><ExternalLink size={14} /> Open</button> : null}
      {received ? (
        <button type="button" class="icon-btn" aria-label="Show in folder" title="Show in folder"
          onClick={() => void showInFolder(first)}><FolderOpen size={16} /></button>
      ) : null}
      <button type="button" class="icon-btn" aria-label="Remove from list" title="Remove from list"
        onClick={() => forgetTransfer(t.id)}><X size={16} /></button>
    </>
  );
}

function Row({ t }: { t: Transfer }) {
  const Icon = t.direction === "send" ? ArrowUpFromLine : ArrowDownToLine;
  const pct = t.total ? Math.min(100, Math.round((t.done / t.total) * 100)) : 0;
  return (
    <li class="hist-row share-row">
      <span class="share-dir" aria-hidden="true"><Icon size={16} /></span>
      <div class="share-main">
        <FileName name={title(t)} class="hist-name" />
        <span class="hist-meta">{meta(t)}</span>
        {t.status === "running" ? (
          <div class="progress share-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div class="bar"><i style={{ width: `${pct}%` }} /></div>
          </div>
        ) : null}
        {t.status === "failed" && t.error ? (
          <span class="share-error"><TriangleAlert size={14} /> {t.error.message}</span>
        ) : null}
      </div>
      <div class="hist-actions"><Actions t={t} /></div>
    </li>
  );
}

/** Files going to or coming from other devices, newest first. */
export function Transfers({ transfers }: { transfers: ReadonlyMap<string, Transfer> }) {
  const list = [...transfers.values()].reverse();
  if (!list.length) return null;
  return (
    <section aria-label="Transfers">
      <h2 class="hist-day">Transfers</h2>
      <ul class="hist-list">{list.map((t) => <Row key={t.id} t={t} />)}</ul>
    </section>
  );
}
