import { useEffect, useState } from "preact/hooks";
import { ArrowLeft, Loader, TriangleAlert, X } from "lucide-preact";
import { inTauri } from "../engine/client";
import { pickFiles } from "../engine/files";
import { loadForm } from "../options";
import type { FormSpec, Opts } from "../options/types";
import { addFiles, replaceOrder, useSession } from "../state/session";
import { getTool } from "../tools/registry";
import { NotFound } from "../tools/ToolPage";
import { useWindowDrop } from "../ui/useDrop";
import { Stage } from "./Stage";
import { useRun } from "./useRun";

function useForm(id: string | null) {
  const [spec, setSpec] = useState<FormSpec | null>(null);
  const [opts, setOpts] = useState<Opts>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    loadForm(id)
      .then((loaded) => {
        if (!alive) return;
        setSpec(loaded);
        setOpts(loaded.defaults);
      })
      .catch(() => alive && setFailed(true));
    return () => { alive = false; };
  }, [id]);

  const set = (patch: Opts) => setOpts((current) => ({ ...current, ...patch }));
  return { spec, opts, set, failed };
}

export function Workspace({ id }: { id: string }) {
  const tool = getTool(id);
  const { files } = useSession();
  const { spec, opts, set, failed } = useForm(tool?.form ?? null);
  const run = useRun(tool ?? getTool("merge")!, spec, opts, files);
  const accepts = tool?.accepts ?? [];
  const limit = tool?.max ?? null;

  const drop = useWindowDrop(accepts, (paths) => addFiles(paths, limit));

  useEffect(() => {
    // Browser previews have no file picker, so open with sample files.
    if (inTauri || !tool || files.length > 0 || tool.min === 0) return;
    void import("../engine/mock").then((m) => addFiles(m.mockPick(tool.accepts, tool.max !== 1), tool.max));
  }, [id]);

  if (!tool) return <NotFound />;
  const Icon = tool.icon;
  const ready = files.length > 0 && files.every((f) => f.status === "ready");
  const enough = files.length >= tool.min;
  const problem = spec?.check?.(opts, files) ?? null;
  const waiting = files.length > 0 && !ready;
  const canRun = !!spec && enough && (files.length === 0 || ready) && !problem && run.state.phase === "idle";
  const hint = !enough ? `Add ${tool.min - files.length} more ${tool.min - files.length === 1 ? "file" : "files"} to continue.`
    : waiting ? "Waiting for your files to open." : problem;

  const add = async () => {
    const paths = await pickFiles({ accepts: tool.accepts, multiple: true });
    if (paths.length) addFiles(paths, limit);
  };
  const move = (from: number, to: number) => {
    const next = [...files];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    replaceOrder(next);
  };
  const running = run.state.phase === "running";

  return (
    <div class={drop.hovering ? "page workpage dragging" : "page workpage"}>
      <div class="work">
        <section class="stage" aria-label="Files">
          <div class="stage-bar">
            <a class="back" href={`#/tool/${tool.id}`}><ArrowLeft size={16} /> Back</a>
            <h1 class="stage-title">{tool.name}</h1>
          </div>
          <div class="stage-body">
            <Stage
              tool={tool}
              files={files}
              canAdd={tool.max === null || files.length < tool.max}
              onAdd={() => void add()}
              onMove={move}
            />
          </div>
          {drop.notice ? <p class="notice" role="status">{drop.notice}</p> : null}
        </section>

        <aside class="side" aria-label="Options">
          <div class="side-head">
            <span class={`side-icon cat-${tool.category}`}><Icon size={18} /></span>
            <h2>Options</h2>
          </div>
          <div class="side-body">
            {spec ? <spec.Form value={opts} set={set} ctx={{ files, reorder: replaceOrder }} /> : null}
            {!spec && !failed ? <p class="hint">Loading options.</p> : null}
            {failed ? <p class="hint">These options could not load. Go back and try again.</p> : null}
          </div>
          <div class="side-foot">
            {run.state.error ? (
              <p class="error" role="alert"><TriangleAlert size={16} /> <span>{run.state.error}</span></p>
            ) : null}
            {run.state.note ? <p class="note" role="status">{run.state.note}</p> : null}
            {running ? (
              <div class="progress" role="status">
                <div class="bar"><i style={{ width: `${Math.round(run.state.value * 100)}%` }} /></div>
                <div class="progress-row">
                  <span><Loader size={14} class="spin" /> {run.state.message || "Working"}</span>
                  <button type="button" class="btn small" onClick={run.cancel}><X size={14} /> Cancel</button>
                </div>
              </div>
            ) : (
              <>
                {hint ? <p class="hint tight">{hint}</p> : null}
                <button type="button" class="btn big primary action" disabled={!canRun} onClick={() => void run.start()}>
                  {tool.action}
                </button>
              </>
            )}
          </div>
        </aside>
        {drop.hovering ? <div class="drop-veil"><span>Drop to add files</span></div> : null}
      </div>
    </div>
  );
}
