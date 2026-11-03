import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  ArrowLeft, FilePlus, FileText, Loader, Plus, RotateCcw, RotateCw, Redo2, Trash2, TriangleAlert, Undo2, X,
} from "lucide-preact";
import { inTauri } from "../../engine/client";
import { addFiles } from "../../state/session";
import { getInfo, pickFiles, startCall, useSession, setDone, go, useWindowDrop, FileName } from "../kit";
import { useReorder } from "../../ui/useReorder";
import { blocker } from "../gate/PasswordGate";
import { addBlank, moveMany, pagesOf, remove, selectRange, toArgs, turn } from "./model";
import type { PageItem, Source } from "./model";
import { Tile } from "./Tile";
import { useHistory } from "./useHistory";
import "./organize.css";

async function readSource(path: string, name: string, password?: string): Promise<Source> {
  const info = await getInfo(path, password);
  if (info.needs_password) throw new Error(`${name} is locked. Remove its password with the Unlock tool first, then add it again.`);
  return { path, name, pages: info.pages, sizes: info.sizes };
}

const baseName = (path: string) => path.split(/[\\/]/).pop() ?? path;

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export default function Organize() {
  const { files } = useSession();
  const main = files[0];
  const history = useHistory<PageItem[]>([]);
  const items = history.value;
  const [sources, setSources] = useState<Source[]>([]);
  const [selection, setSelection] = useState<ReadonlySet<number>>(new Set());
  const [anchor, setAnchor] = useState(0);
  const [focus, setFocus] = useState(0);
  const [size, setSize] = useState(150);
  const [note, setNote] = useState<string | null>(null);
  const [run, setRun] = useState<{ value: number; message: string } | null>(null);
  const grid = useRef<HTMLDivElement>(null);
  const cancel = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    // Browser previews have no file picker, so open with a sample file.
    if (inTauri || files.length) return;
    void import("../../engine/mock").then((m) => addFiles(m.mockPick(["pdf"], false), 1));
  }, []);

  const mainReady = main?.status === "ready";
  useEffect(() => {
    if (!mainReady || !main || sources.some((s) => s.path === main.path)) return;
    void readSource(main.path, main.name, main.password).then((source) => {
      setSources([source]);
      history.reset(pagesOf(source));
    }).catch((e: Error) => setNote(e.message));
  }, [mainReady, main?.path]);

  const sourceMap = useMemo(() => new Map(sources.map((s) => [s.path, s])), [sources]);

  const addPdfs = async (paths: string[]) => {
    const loaded: Source[] = [];
    const added: PageItem[] = [];
    for (const path of paths.filter((p) => p.toLowerCase().endsWith(".pdf"))) {
      try {
        const known = sourceMap.get(path) ?? loaded.find((s) => s.path === path);
        const source = known ?? await readSource(path, baseName(path));
        if (!known) loaded.push(source);
        added.push(...pagesOf(source));
      } catch (e) {
        setNote((e as Error).message);
      }
    }
    if (!added.length) return;
    setSources((s) => [...s, ...loaded]);
    history.set([...items, ...added]);
    setNote(null);
  };
  const drop = useWindowDrop(["pdf"], (paths) => void addPdfs(paths));
  const choose = async () => {
    const paths = await pickFiles({ accepts: ["pdf"], multiple: true, title: "Add PDF files" });
    if (paths.length) await addPdfs(paths);
  };

  const rotate = (deg: number) => history.set(turn(items, selection.size ? selection : new Set(items.map((p) => p.id)), deg));
  const canDelete = selection.size > 0 && selection.size < items.length;
  const deleteSelected = () => {
    if (!canDelete) return;
    history.set(remove(items, selection));
    setSelection(new Set());
  };
  const reset = () => {
    const first = sources[0];
    if (!first) return;
    setSources([first]);
    history.reset(pagesOf(first));
    setSelection(new Set());
  };

  const reorder = useReorder({
    onReorder: (from, slot) => {
      const grabbed = items[from].id;
      const active = selection.has(grabbed) ? selection : new Set([grabbed]);
      setSelection(active);
      history.set(moveMany(items, from, slot, active));
    },
  });

  const select = (index: number, e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }) => {
    const id = items[index].id;
    setFocus(index);
    if (e.shiftKey) {
      setSelection(selectRange(items, anchor, index));
      return;
    }
    setAnchor(index);
    if (e.ctrlKey || e.metaKey) {
      const next = new Set(selection);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      setSelection(next);
    } else {
      setSelection(new Set([id]));
    }
  };

  const moveFocus = (to: number) => {
    const clamped = Math.max(0, Math.min(items.length - 1, to));
    setFocus(clamped);
    grid.current?.querySelector<HTMLElement>(`[data-ri="${clamped}"]`)?.focus();
  };
  const columns = () => {
    const tiles = Array.from(grid.current?.children ?? []) as HTMLElement[];
    const first = tiles[0]?.offsetTop;
    const n = tiles.findIndex((t) => t.offsetTop !== first);
    return n < 0 ? Math.max(tiles.length, 1) : n;
  };

  const onKey = (e: KeyboardEvent) => {
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();
    if (e.altKey) return;
    const arrows: Record<string, number> = { arrowright: 1, arrowleft: -1, arrowdown: columns(), arrowup: -columns() };
    if (mod && key === "z") { e.preventDefault(); history.undo(); }
    else if (mod && key === "y") { e.preventDefault(); history.redo(); }
    else if (mod && key === "a") { e.preventDefault(); setSelection(new Set(items.map((p) => p.id))); }
    else if (key === "delete" || key === "backspace") { e.preventDefault(); deleteSelected(); }
    else if (key in arrows) { e.preventDefault(); moveFocus(focus + arrows[key]); }
    else if (key === " " || key === "enter") { e.preventDefault(); select(focus, e); }
    else if (key === "r" && !mod) rotate(e.shiftKey ? -90 : 90);
    else if (key === "escape") setSelection(new Set());
  };

  const save = async () => {
    if (!main || run) return;
    setNote(null);
    setRun({ value: 0, message: "Starting" });
    const call = startCall("organize", toArgs(main.path, items, main.password), (p) =>
      setRun({ value: p.value, message: p.message ?? "Working" }));
    cancel.current = call.cancel;
    try {
      const result = await call.promise;
      setDone({ toolId: "organize", result });
      go("result/organize");
    } catch (error) {
      const failure = error as { code?: string; message?: string };
      setNote(failure.code === "cancelled" ? "Stopped. Nothing was saved." : failure.message ?? "Something went wrong. Try again.");
    } finally {
      setRun(null);
      cancel.current = null;
    }
  };

  const gate = !main ? (
    <div class="gate"><div class="gate-card"><FileText size={26} /><p>Choose a PDF to organize first.</p><a class="btn primary" href="#/tool/organize">Choose a PDF</a></div></div>
  ) : blocker([main]);

  const changed = history.canUndo || items.length !== sources[0]?.pages;
  return (
    <div class={drop.hovering ? "page dragging" : "page"}>
      <div class="org" onKeyDown={onKey}>
        <div class="org-bar">
          <a class="back" href="#/tool/organize"><ArrowLeft size={16} /> Back</a>
          <h1 class="stage-title">Organize pages</h1>
          {main ? <FileName name={main.name} class="org-file" /> : null}
          <span class="org-count">{plural(items.length, "page")}{selection.size ? `, ${selection.size} selected` : ""}</span>
          <span class="grow" />
          <label class="org-size">Size
            <input type="range" min={110} max={230} value={size} aria-label="Thumbnail size"
              onInput={(e) => setSize(Number(e.currentTarget.value))} />
          </label>
        </div>
        <div class="org-tools" role="toolbar" aria-label="Page tools">
          <button type="button" class="btn small" disabled={!history.canUndo} onClick={history.undo} title="Undo (Ctrl+Z)"><Undo2 size={15} /> Undo</button>
          <button type="button" class="btn small" disabled={!history.canRedo} onClick={history.redo} title="Redo (Ctrl+Y)"><Redo2 size={15} /> Redo</button>
          <i class="sep" />
          <button type="button" class="btn small" onClick={() => rotate(-90)} title="Rotate left (Shift+R)"><RotateCcw size={15} /> Rotate left</button>
          <button type="button" class="btn small" onClick={() => rotate(90)} title="Rotate right (R)"><RotateCw size={15} /> Rotate right</button>
          <button type="button" class="btn small" disabled={!canDelete} onClick={deleteSelected} title="Delete (Delete key)"><Trash2 size={15} /> Delete</button>
          <button type="button" class="btn small" onClick={() => history.set(addBlank(items, selection))}><Plus size={15} /> Blank page</button>
          <button type="button" class="btn small" onClick={() => void choose()}><FilePlus size={15} /> Add PDF</button>
          <button type="button" class="btn small" disabled={!changed} onClick={reset}>Start over</button>
          <span class="org-hint">{selection.size ? "Rotate and delete act on the selected pages." : "Nothing selected: rotate turns every page."}</span>
        </div>

        {gate ?? (
          <div class="org-scroll" onClick={(e) => { if (e.target === e.currentTarget) setSelection(new Set()); }}>
            <div class="org-grid" ref={grid} role="listbox" aria-multiselectable="true" aria-label="Pages" style={{ "--tile": `${size}px` }}>
              {items.map((item, index) => (
                <Tile
                  key={item.id}
                  item={item}
                  position={index + 1}
                  source={item.blank ? sources[0] : sourceMap.get(item.source)}
                  main={item.source === main?.path}
                  size={size}
                  selected={selection.has(item.id)}
                  focused={focus === index}
                  state={reorder.stateOf(index, items.length)}
                  drag={reorder.itemProps(index)}
                  password={main?.password}
                  onSelect={(e) => select(index, e)}
                />
              ))}
            </div>
            <p class="hint org-foot">Click to select, Ctrl or Shift to select more. Drag pages to reorder, or hold Alt and press an arrow key. Drop PDF files here to add them.</p>
          </div>
        )}

        <div class="org-actions">
          {note ? <p class="error" role="alert"><TriangleAlert size={16} /> <span>{note}</span></p> : null}
          {run ? (
            <div class="progress org-progress" role="status">
              <div class="bar"><i style={{ width: `${Math.round(run.value * 100)}%` }} /></div>
              <div class="progress-row">
                <span><Loader size={14} class="spin" /> {run.message}</span>
                <button type="button" class="btn small" onClick={() => void cancel.current?.()}><X size={14} /> Cancel</button>
              </div>
            </div>
          ) : (
            <button type="button" class="btn big primary" disabled={!items.length || !mainReady || !changed} onClick={() => void save()}>
              Save changes
            </button>
          )}
        </div>
        {drop.hovering ? <div class="drop-veil"><span>Drop to add pages</span></div> : null}
      </div>
    </div>
  );
}
