import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { engineCall } from "../kit";
import { setFiles } from "../../state/session";
import { replaceTab, setLeaveGuard } from "../../state/tabs";
import { TOOL_COLOR, toEngineItems } from "./annots";
import type { Tool } from "./annots";
import { PageLayer } from "./PageLayer";
import { PrintDialog, PrintSheet } from "./Print";
import type { PrintJob } from "./Print";
import { Sidebar } from "./Sidebar";
import type { Size } from "./Shapes";
import { lastPage, lastZoom, saveBookmarks, saveLastPage, saveZoom } from "./store";
import { Toolbar } from "./Toolbar";
import { ToolPanel } from "./ToolPanel";
import { useAnnots } from "./useAnnots";
import { nextBookmark, useBookmarks } from "./useBookmarks";
import { useSearch } from "./useSearch";
import { layoutRows, useKeepPosition, useVisibleRows } from "./virtual";

export interface ViewerProps {
  path: string;
  name: string;
  password?: string;
  sizes: readonly Size[];
  onNotice: (notice: Notice) => void;
}

const PAD = 24;
const GAP = 16;
const CSS_PER_POINT = 96 / 72;
const STEPS = [25, 50, 75, 100, 125, 150, 200, 300, 400, 500];

export type Notice = { kind: "ok"; path: string; name: string } | { kind: "error"; message: string } | null;

function imageWidthFor(pointsWide: number, scale: number): number {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  return Math.max(400, Math.min(3800, Math.ceil((pointsWide * scale * dpr) / 200) * 200));
}

export function Viewer({ path, name, password, sizes, onNotice }: ViewerProps) {
  const box = useRef<HTMLDivElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  const [boxWidth, setBoxWidth] = useState(0);
  const [zoom, setZoom] = useState<"fit" | number>(lastZoom);
  const [tool, setTool] = useState<Tool>("select");
  const [colors, setColors] = useState(TOOL_COLOR);
  const [sidebar, setSidebar] = useState(true);
  const [printing, setPrinting] = useState<"dialog" | PrintJob | null>(null);
  const [saving, setSaving] = useState(false);
  const annots = useAnnots();
  const bookmarks = useBookmarks(path, sizes.length);
  const curRef = useRef(0);

  const scale = zoom === "fit"
    ? Math.max(0.2, (boxWidth - PAD * 2 - 6) / (sizes[0]?.[0] ?? 595))
    : (zoom / 100) * CSS_PER_POINT;
  const zoomPct = Math.round((scale / CSS_PER_POINT) * 100);
  const heights = useMemo(() => sizes.map((s) => s[1] * scale), [sizes, scale]);
  const layout = useMemo(() => layoutRows(heights, GAP, PAD), [heights]);
  const vis = useVisibleRows(box, layout, heights);
  useKeepPosition(box, layout, scale);
  curRef.current = vis.current;

  const [renderScale, setRenderScale] = useState(scale);
  useEffect(() => {
    const timer = window.setTimeout(() => setRenderScale(scale), 160);
    return () => window.clearTimeout(timer);
  }, [scale]);

  const search = useSearch(path, password, () => curRef.current);
  const widest = Math.max(...sizes.map((s) => s[0]), 1) * scale;
  const contentWidth = Math.max(boxWidth, widest + PAD * 2);

  const goTo = (page: number, smooth = false) => {
    const target = Math.max(0, Math.min(sizes.length - 1, page));
    box.current?.scrollTo({ top: Math.max(0, layout.tops[target] - 8), behavior: smooth ? "smooth" : "auto" });
  };

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const read = () => setBoxWidth(el.clientWidth);
    read();
    const watch = new ResizeObserver(read);
    watch.observe(el);
    return () => watch.disconnect();
  }, []);

  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || !boxWidth || !box.current) return;
    restored.current = true;
    const page = Math.min(lastPage(path), sizes.length - 1);
    box.current.scrollTop = Math.max(0, layout.tops[page] - 8);
  }, [boxWidth]);

  useEffect(() => {
    if (!restored.current) return;
    const timer = window.setTimeout(() => saveLastPage(path, vis.current), 400);
    return () => window.clearTimeout(timer);
  }, [vis.current]);
  useEffect(() => () => saveLastPage(path, curRef.current), [path]);

  const hit = search.state.flat[search.state.current];
  useEffect(() => {
    if (!hit || !box.current) return;
    const y = layout.tops[hit.page] + hit.rect[1] * scale;
    const top = box.current.scrollTop;
    const view = box.current.clientHeight;
    if (y < top + 40 || y > top + view - 80) box.current.scrollTo({ top: Math.max(0, y - view * 0.35) });
  }, [search.state.current, search.state.flat]);

  const applyZoom = (next: "fit" | number) => {
    setZoom(next);
    saveZoom(next);
  };
  const zoomBy = (dir: 1 | -1) => {
    const pct = zoomPct;
    const next = dir > 0 ? STEPS.find((s) => s > pct + 1) : [...STEPS].reverse().find((s) => s < pct - 1);
    applyZoom(next ?? (dir > 0 ? 500 : 25));
  };
  const wheelZoom = useRef<(e: WheelEvent) => void>();
  wheelZoom.current = (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    applyZoom(Math.max(25, Math.min(500, Math.round(zoomPct * (e.deltaY < 0 ? 1.1 : 0.9)))));
  };
  useEffect(() => {
    const el = box.current;
    const fn = (e: WheelEvent) => wheelZoom.current?.(e);
    el?.addEventListener("wheel", fn, { passive: false });
    return () => el?.removeEventListener("wheel", fn);
  }, []);

  const chooseTool = (t: Tool) => { setTool(t); annots.deselect(); };
  const chooseColor = (c: string) => {
    const target = tool === "select" ? "highlight" : tool;
    if (tool === "select") setTool("highlight");
    setColors({ ...colors, [target]: c });
  };
  const color = colors[tool === "select" ? "highlight" : tool];

  const save = async () => {
    if (!annots.list.length || saving) return;
    setSaving(true);
    onNotice(null);
    try {
      const result = await engineCall("annotate", { file: path, items: toEngineItems(annots.list), ...(password ? { password } : {}) });
      const out = result.outputs[0].path;
      saveLastPage(out, curRef.current);
      saveBookmarks(out, bookmarks.list);
      onNotice({ kind: "ok", path: out, name: out.split(/[\\/]/).pop() ?? out });
      annots.clear();
      replaceTab(path, out);
      setFiles([out]);
    } catch (e) {
      onNotice({ kind: "error", message: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const startPrint = (pages: number[]) =>
    setPrinting({ file: path, password, pages, sizes, annots: annots.list });
  const canLeave = () => !annots.list.length || window.confirm("You have marks that are not saved. Leave without saving them?");
  const leave = (e: Event) => {
    if (!canLeave()) e.preventDefault();
  };
  const leaveCheck = useRef(canLeave);
  leaveCheck.current = canLeave;
  useEffect(() => {
    setLeaveGuard(() => leaveCheck.current());
    return () => setLeaveGuard(null);
  }, []);

  const latest = useRef<(e: KeyboardEvent) => void>();
  latest.current = (e) => {
    const typing = (e.target as HTMLElement).closest?.("input, textarea");
    const mod = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();
    if (mod && key === "f") { e.preventDefault(); searchBox.current?.focus(); searchBox.current?.select(); return; }
    if (mod && key === "g") { e.preventDefault(); document.querySelector<HTMLInputElement>("[data-pagejump]")?.focus(); return; }
    if (mod && key === "p") { e.preventDefault(); setPrinting("dialog"); return; }
    if (mod && key === "s") { e.preventDefault(); void save(); return; }
    if (mod && (key === "=" || key === "+")) { e.preventDefault(); zoomBy(1); return; }
    if (mod && key === "-") { e.preventDefault(); zoomBy(-1); return; }
    if (mod && key === "0") { e.preventDefault(); applyZoom("fit"); return; }
    if (mod && key === "1") { e.preventDefault(); applyZoom(100); return; }
    if (typing) return;
    if (mod && key === "z") { e.preventDefault(); annots.undo(); return; }
    if (key === "escape") { annots.deselect(); setTool("select"); setPrinting(null); return; }
    if (key === "delete" || key === "backspace") { if (annots.removeSelected()) e.preventDefault(); return; }
    if (mod || e.altKey) return;
    if (key === "b") {
      e.preventDefault();
      const target = nextBookmark(bookmarks.list, curRef.current);
      if (!e.shiftKey) bookmarks.toggle(curRef.current);
      else if (target !== null) goTo(target);
      return;
    }
    const tools: Record<string, Tool> = { v: "select", h: "highlight", u: "underline", n: "note", p: "pen" };
    if (tools[key]) { chooseTool(tools[key]); return; }
    if (key === "arrowright") { e.preventDefault(); goTo(curRef.current + 1, true); }
    else if (key === "arrowleft") { e.preventDefault(); goTo(curRef.current - 1, true); }
    else if (key === "home") { e.preventDefault(); goTo(0); }
    else if (key === "end") { e.preventDefault(); goTo(sizes.length - 1); }
    else if (key === "f3" || key === "g") { e.preventDefault(); search.step(e.shiftKey ? -1 : 1); }
  };
  useEffect(() => {
    const fn = (e: KeyboardEvent) => latest.current?.(e);
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, []);
  useEffect(() => box.current?.focus(), []);

  const marks = useMemo(() => new Map([...search.byPage].map(([p, r]) => [p, r.length])), [search.byPage]);
  const slots = [];
  for (let page = vis.first; page <= vis.last; page += 1) {
    const size = sizes[page];
    const here = hit && hit.page === page ? hit.index : null;
    slots.push(
      <div class="rd-slot" key={page} style={{ top: `${layout.tops[page]}px`, height: `${heights[page]}px`, width: `${Math.max(boxWidth, size[0] * scale + PAD * 2)}px` }}>
        <PageLayer
          file={path} password={password} page={page} size={size} scale={scale}
          imageWidth={imageWidthFor(size[0], renderScale)}
          distance={() => Math.abs(page - curRef.current)}
          tool={tool} color={color} bookmarked={bookmarks.list.includes(page)}
          annots={annots.list.filter((a) => a.page === page)}
          selected={annots.selected} editing={annots.editing}
          hits={search.byPage.get(page) ?? []} currentHit={here}
          onAdd={annots.add} onPick={annots.pick} onNoteText={annots.setNoteText}
        />
      </div>,
    );
  }

  return (
    <div class="reader">
      <Toolbar
        name={name} page={vis.current} pages={sizes.length} zoomPct={zoomPct} fit={zoom === "fit"} sidebar={sidebar}
        tool={tool} color={color} pending={annots.list.length} saving={saving} search={search.state} searchBox={searchBox}
        bookmarks={bookmarks.list} onBookmark={() => bookmarks.toggle(vis.current)}
        onBack={leave} onSidebar={() => setSidebar(!sidebar)} onGo={(p) => goTo(p)} onZoom={zoomBy}
        onFit={() => applyZoom("fit")} onTool={chooseTool} onColor={chooseColor} onUndo={annots.undo} onSave={() => void save()}
        onPrint={() => setPrinting("dialog")} onSearch={(q) => void search.run(q)} onStep={search.step} onClear={search.clear}
      />
      <div class="rd-body">
        {sidebar ? <Sidebar file={path} password={password} sizes={sizes} current={vis.current} marks={marks} bookmarks={bookmarks.list} onGo={(p) => goTo(p)} /> : null}
        <div class="rd-scroll" ref={box} tabIndex={0} aria-label="Document pages" onPointerDown={() => annots.deselect()}>
          <div class="rd-content" style={{ width: `${contentWidth}px`, height: `${layout.total}px` }}>{slots}</div>
        </div>
        <ToolPanel canLeave={canLeave} />
        {printing === "dialog" ? (
          <PrintDialog count={sizes.length} current={vis.current} onClose={() => setPrinting(null)} onPrint={startPrint} />
        ) : null}
        {printing && printing !== "dialog" ? <PrintSheet job={printing} onDone={() => setPrinting(null)} /> : null}
      </div>
    </div>
  );
}
