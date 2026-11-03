import { useEffect, useState } from "preact/hooks";
import { Check, FileText, FolderOpen, TriangleAlert, X } from "lucide-preact";
import { getInfo, pickFiles, showInFolder, useSession } from "../kit";
import { inTauri } from "../../engine/client";
import { recordOpen } from "../../state/history";
import { addFiles, setFiles } from "../../state/session";
import { ensureTab } from "../../state/tabs";
import { blocker } from "../gate/PasswordGate";
import type { Size } from "./Shapes";
import { Viewer } from "./Viewer";
import type { Notice } from "./Viewer";
import "./reader.css";

const A4: Size = [595, 842];

function Toast({ notice, onClose }: { notice: NonNullable<Notice>; onClose: () => void }) {
  const ok = notice.kind === "ok";
  return (
    <div class={ok ? "rd-toast" : "rd-toast bad"} role="status">
      {ok ? <Check size={16} /> : <TriangleAlert size={16} />}
      <span>{ok ? `Saved as a new copy: ${notice.name}` : notice.message}</span>
      {ok ? <button type="button" class="btn small" onClick={() => void showInFolder(notice.path)}><FolderOpen size={14} /> Show in folder</button> : null}
      <button type="button" class="icon-btn" aria-label="Dismiss" onClick={onClose}><X size={15} /></button>
    </div>
  );
}

/** The reader: continuous pages, search, zoom, thumbnails and marks that save through the annotate tool. */
export default function Reader() {
  const { files } = useSession();
  const main = files[0];
  const [sizes, setSizes] = useState<{ path: string; list: Size[] } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    // Browser previews have no file picker, so open with a sample file.
    if (inTauri || files.length) return;
    void import("../../engine/mock").then((m) => addFiles(m.mockPick(["pdf"], false), 1));
  }, []);

  useEffect(() => {
    if (!main || main.status !== "ready") return;
    let alive = true;
    setProblem(null);
    getInfo(main.path, main.password).then((info) => {
      if (!alive) return;
      const list = info.sizes.length === info.pages ? info.sizes : Array.from({ length: info.pages }, () => A4);
      setSizes({ path: main.path, list });
      recordOpen(main.path);
      ensureTab(main.path);
    }).catch((e: Error) => alive && setProblem(e.message));
    return () => { alive = false; };
  }, [main?.path, main?.status, main?.password]);

  const choose = async () => {
    const paths = await pickFiles({ accepts: ["pdf"], multiple: false, title: "Choose a PDF to read" });
    if (paths.length) setFiles(paths.slice(0, 1));
  };

  const gate = !main ? (
    <div class="gate"><div class="gate-card"><FileText size={26} /><p>Choose a PDF to read.</p>
      <button type="button" class="btn primary" onClick={() => void choose()}>Choose a PDF</button></div></div>
  ) : blocker([main]);

  const ready = main && sizes?.path === main.path && sizes.list.length > 0 ? sizes : null;
  return (
    <div class="page readerpage">
      {gate}
      {!gate && problem ? <div class="gate"><div class="gate-card"><TriangleAlert size={26} /><p>{problem}</p><a class="btn" href="#/">Back to all tools</a></div></div> : null}
      {!gate && !problem && !ready ? <div class="gate"><span class="gate-wait">Opening your file</span></div> : null}
      {!gate && ready && main ? (
        <Viewer key={main.path} path={main.path} name={main.name} password={main.password} sizes={ready.list} onNotice={setNotice} />
      ) : null}
      {notice ? <Toast notice={notice} onClose={() => setNotice(null)} /> : null}
    </div>
  );
}
