import type { ComponentChildren } from "preact";
import { ArrowLeft, Loader, Maximize2, Minus, Plus, Redo2, TriangleAlert, Undo2, X } from "lucide-preact";
import { getTool } from "../../tools/registry";
import { pickFiles } from "../../engine/files";
import { addFiles } from "../../state/session";
import { PageCanvas } from "./PageCanvas";
import type { PageCanvasProps } from "./PageCanvas";
import { PageStrip } from "./PageStrip";
import type { DocState } from "./useEditorDoc";
import type { EditorRunState } from "./useEditorRun";
import type { DocView, Item } from "./types";
import { useZoom } from "./useZoom";
import "./canvas.css";

/** Shows the loading, empty and error states, and the editor once the file is ready. */
export function DocGate(props: { state: DocState; children: (doc: DocView) => ComponentChildren }) {
  const s = props.state;
  if (s.status === "ready") return <>{props.children(s.doc)}</>;
  const choose = async () => {
    const paths = await pickFiles({ accepts: ["pdf"], multiple: false, title: "Choose a PDF" });
    if (paths.length) addFiles(paths, 1);
  };
  return (
    <div class="page">
      <main class="ed-empty">
        {s.status === "loading" ? <p><Loader size={18} class="spin" /> Opening your file</p> : null}
        {s.status === "error" ? <p class="ed-warn" role="alert"><TriangleAlert size={16} /> {s.message}</p> : null}
        {s.status === "empty" ? (
          <>
            <h2>Choose a PDF to start</h2>
            <button type="button" class="btn primary" onClick={() => void choose()}>Choose a PDF</button>
          </>
        ) : null}
        <a class="back" href="#/">Back to all tools</a>
      </main>
    </div>
  );
}

export interface ShellProps<T extends Item> {
  toolId: string;
  doc: DocView;
  page: number;
  onPage: (page: number) => void;
  counts: readonly number[];
  tools: ComponentChildren;
  sidebar: ComponentChildren;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  action: { label: string; disabled: boolean; hint?: string | null; onClick: () => void };
  run: { state: EditorRunState; cancel: () => void };
  canvas: Omit<PageCanvasProps<T>, "doc" | "page" | "scale">;
  status?: ComponentChildren;
}

/** Page strip, toolbar, zoomable page canvas and an options sidebar with the action button. */
export function EditorShell<T extends Item>(props: ShellProps<T>) {
  const tool = getTool(props.toolId);
  const Icon = tool?.icon;
  const size = props.doc.sizes[props.page] ?? { w: 595, h: 842 };
  const zoom = useZoom(size.w);
  const { state } = props.run;

  const onWheel = (e: WheelEvent) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    if (e.deltaY < 0) zoom.zoomIn(); else zoom.zoomOut();
  };

  return (
    <div class="page workpage">
      <div class="ed">
        <PageStrip doc={props.doc} page={props.page} counts={props.counts} onPage={props.onPage} />
        <section class="ed-main" aria-label="Page">
          <div class="ed-bar">
            <a class="back" href={`#/tool/${props.toolId}`}><ArrowLeft size={16} /> Back</a>
            <span class="ed-grow" />
            <button type="button" class="icon-btn" aria-label="Undo" title="Undo (Ctrl+Z)" disabled={!props.canUndo} onClick={props.onUndo}><Undo2 size={17} /></button>
            <button type="button" class="icon-btn" aria-label="Redo" title="Redo (Ctrl+Y)" disabled={!props.canRedo} onClick={props.onRedo}><Redo2 size={17} /></button>
            <span class="ed-sep" />
            <span class="ed-zoom">
              <button type="button" class="icon-btn" aria-label="Zoom out" onClick={zoom.zoomOut}><Minus size={17} /></button>
              <output aria-live="polite">{Math.round(zoom.zoom * 100)}%</output>
              <button type="button" class="icon-btn" aria-label="Zoom in" onClick={zoom.zoomIn}><Plus size={17} /></button>
              <button type="button" class={zoom.fitted ? "icon-btn on" : "icon-btn"} aria-label="Fit width" title="Fit width" onClick={zoom.fit}><Maximize2 size={16} /></button>
            </span>
          </div>
          <div class="ed-toolrow" role="toolbar" aria-label="Tools">{props.tools}</div>
          <div class="ed-scroll" ref={zoom.area} onWheel={onWheel}>
            <PageCanvas<T> {...props.canvas} doc={props.doc} page={props.page} scale={zoom.scale} />
          </div>
          <div class="ed-pagebar">Page {props.page + 1} of {props.doc.sizes.length}{props.status ? <>{" · "}{props.status}</> : null}</div>
        </section>
        <aside class="side" aria-label="Options">
          <div class="side-head">
            {Icon ? <span class={`side-icon cat-${tool?.category}`}><Icon size={18} /></span> : null}
            <h2>{tool?.name ?? "Options"}</h2>
          </div>
          <div class="side-body">{props.sidebar}</div>
          <div class="side-foot">
            {state.error ? <p class="error" role="alert"><TriangleAlert size={16} /> <span>{state.error}</span></p> : null}
            {state.running ? (
              <div class="progress" role="status">
                <div class="bar"><i style={{ width: `${Math.round(state.value * 100)}%` }} /></div>
                <div class="progress-row">
                  <span><Loader size={14} class="spin" /> {state.message || "Working"}</span>
                  <button type="button" class="btn small" onClick={props.run.cancel}><X size={14} /> Cancel</button>
                </div>
              </div>
            ) : (
              <>
                {props.action.hint ? <p class="hint tight">{props.action.hint}</p> : null}
                <button type="button" class="btn big primary action" disabled={props.action.disabled} onClick={props.action.onClick}>
                  {props.action.label}
                </button>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
