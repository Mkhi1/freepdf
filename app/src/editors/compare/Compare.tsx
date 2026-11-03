import { useEffect, useState } from "preact/hooks";
import { ArrowLeft, ArrowLeftRight, FileText, Loader, TriangleAlert, X } from "lucide-preact";
import { FileName, formatBytes, getInfo, startCall, useSession } from "../kit";
import { replaceOrder } from "../../state/session";
import { blocker } from "../gate/PasswordGate";
import { Results } from "./Results";
import type { ResultInput } from "./Results";
import "./compare.css";

type Mode = "text" | "visual";

/** Visual mode writes one picture per page, so those go to the temp folder the app may display from. */
async function scratchDir(): Promise<string | undefined> {
  const { inTauri } = await import("../../engine/client");
  if (!inTauri) return undefined;
  const { tempDir } = await import("@tauri-apps/api/path");
  return tempDir();
}

const MODES: ReadonlyArray<{ id: Mode; label: string; hint: string }> = [
  { id: "text", label: "Text", hint: "Finds added and removed words. Best for documents with real text." },
  { id: "visual", label: "Visual", hint: "Compares how the pages look. Use it for scans, drawings and layout changes." },
];

function FileBox({ label, file }: { label: string; file: { name: string; pages?: number; bytes?: number } }) {
  return (
    <div class="cmp-file">
      <small>{label}</small>
      <FileName name={file.name} class="cmp-fname" />
      <span class="hint">{file.pages ? `${file.pages} pages` : ""}{file.bytes ? ` · ${formatBytes(file.bytes)}` : ""}</span>
    </div>
  );
}

export default function Compare() {
  const { files } = useSession();
  const [a, b] = files;
  const [mode, setMode] = useState<Mode>("text");
  const [run, setRun] = useState<{ value: number; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState<ResultInput | null>(null);
  const [cancel, setCancel] = useState<(() => Promise<void>) | null>(null);

  useEffect(() => {
    // Browser previews have no file picker, so open with sample files.
    if (files.length >= 2) return;
    void import("../../engine/client").then(async ({ inTauri }) => {
      if (inTauri) return;
      const { mockPick } = await import("../../engine/mock");
      const { setFiles } = await import("../../state/session");
      setFiles(mockPick(["pdf"], true).slice(0, 2));
    });
  }, []);

  const gate = files.length < 2 ? null : blocker([a, b]);
  const ready = files.length === 2 && !gate;

  const start = async () => {
    if (!ready || run) return;
    setError(null);
    setRun({ value: 0, message: "Starting" });
    const out_dir = mode === "visual" ? await scratchDir() : undefined;
    const call = startCall("compare", {
      file_a: a.path, file_b: b.path, mode,
      ...(a.password ? { password: a.password } : {}),
      ...(b.password ? { password_b: b.password } : {}),
      ...(out_dir ? { out_dir } : {}),
    }, (p) => setRun({ value: p.value, message: p.message ?? "Comparing" }));
    setCancel(() => call.cancel);
    try {
      const result = await call.promise;
      const [infoA, infoB] = await Promise.all([getInfo(a.path, a.password), getInfo(b.path, b.password)]);
      setShown({
        result, mode, fileA: a.path, fileB: b.path, passwordA: a.password, passwordB: b.password,
        sizesA: infoA.sizes, sizesB: infoB.sizes,
      });
    } catch (e) {
      const failure = e as { code?: string; message?: string };
      setError(failure.code === "cancelled" ? "Stopped. Nothing was saved." : failure.message ?? "Something went wrong. Try again.");
    } finally {
      setRun(null);
      setCancel(null);
    }
  };

  if (shown) {
    return (
      <div class="page">
        <div class="cmp-top">
          <button type="button" class="back cmp-backbtn" onClick={() => setShown(null)}><ArrowLeft size={16} /> Change files or mode</button>
          <h1 class="stage-title">Comparison</h1>
        </div>
        <Results input={shown} />
      </div>
    );
  }

  return (
    <div class="page">
      <main class="cmp-setup">
        <a class="back" href="#/tool/compare"><ArrowLeft size={16} /> Back</a>
        <h1>Compare two PDFs</h1>
        <p class="lead">Pick the old version and the new version. Differences are marked on the pages and listed so you can jump through them.</p>
        {files.length < 2 ? (
          <div class="gate-card cmp-need"><FileText size={26} /><p>Compare needs two PDF files.</p><a class="btn primary" href="#/tool/compare">Choose files</a></div>
        ) : (
          <div class="cmp-files">
            <FileBox label="Old version" file={files[0]} />
            <button type="button" class="icon-btn cmp-swap" aria-label="Swap old and new" title="Swap old and new"
              onClick={() => replaceOrder([files[1], files[0]])}><ArrowLeftRight size={18} /></button>
            <FileBox label="New version" file={files[1]} />
          </div>
        )}
        {gate}
        <div class="choices compact cmp-modes" role="radiogroup" aria-label="Compare by">
          {MODES.map((m) => (
            <button type="button" role="radio" aria-checked={mode === m.id} class={mode === m.id ? "choice on" : "choice"} onClick={() => setMode(m.id)}>
              <span class="choice-label">{m.label}</span>
              <span class="choice-hint">{m.hint}</span>
            </button>
          ))}
        </div>
        {error ? <p class="error" role="alert"><TriangleAlert size={16} /> <span>{error}</span></p> : null}
        {run ? (
          <div class="progress cmp-progress" role="status">
            <div class="bar"><i style={{ width: `${Math.round(run.value * 100)}%` }} /></div>
            <div class="progress-row">
              <span><Loader size={14} class="spin" /> {run.message}</span>
              <button type="button" class="btn small" onClick={() => void cancel?.()}><X size={14} /> Cancel</button>
            </div>
          </div>
        ) : (
          <button type="button" class="btn big primary" disabled={!ready} onClick={() => void start()}>Compare</button>
        )}
      </main>
    </div>
  );
}
