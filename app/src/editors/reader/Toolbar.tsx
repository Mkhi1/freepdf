import { useEffect, useRef, useState } from "preact/hooks";
import {
  ArrowLeft, Bookmark, ChevronDown, ChevronUp, Highlighter, MousePointer2, PanelLeft, Pen, Printer, Save, Search, StickyNote,
  Underline, Undo2, X, ZoomIn, ZoomOut, MoveHorizontal,
} from "lucide-preact";
import { FileName } from "../kit";
import { COLORS } from "./annots";
import type { Tool } from "./annots";
import { nextBookmark } from "./useBookmarks";
import type { SearchState } from "./useSearch";

const TOOLS: ReadonlyArray<{ id: Tool; label: string; key: string; Icon: typeof Pen }> = [
  { id: "select", label: "Select and move", key: "V", Icon: MousePointer2 },
  { id: "highlight", label: "Highlight: drag a box over the text", key: "H", Icon: Highlighter },
  { id: "underline", label: "Underline: drag a box over the text", key: "U", Icon: Underline },
  { id: "note", label: "Sticky note: click where it goes", key: "N", Icon: StickyNote },
  { id: "pen", label: "Pen: draw freehand", key: "P", Icon: Pen },
];

export interface ToolbarProps {
  name: string;
  page: number;
  pages: number;
  zoomPct: number;
  fit: boolean;
  sidebar: boolean;
  tool: Tool;
  color: string;
  pending: number;
  saving: boolean;
  search: SearchState;
  searchBox: { current: HTMLInputElement | null };
  bookmarks: readonly number[];
  onBookmark: () => void;
  onBack: (e: Event) => void;
  onSidebar: () => void;
  onGo: (page: number) => void;
  onZoom: (direction: 1 | -1) => void;
  onFit: () => void;
  onTool: (t: Tool) => void;
  onColor: (c: string) => void;
  onUndo: () => void;
  onSave: () => void;
  onPrint: () => void;
  onSearch: (q: string) => void;
  onStep: (d: number) => void;
  onClear: () => void;
}

function PageBox({ page, pages, onGo }: Pick<ToolbarProps, "page" | "pages" | "onGo">) {
  const [text, setText] = useState(String(page + 1));
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setText(String(page + 1)); }, [page]);
  const commit = () => {
    editing.current = false;
    const n = Number(text);
    if (Number.isInteger(n) && n >= 1 && n <= pages) onGo(n - 1);
    else setText(String(page + 1));
  };
  return (
    <label class="rd-pagebox">
      <input
        data-pagejump
        class="input"
        inputMode="numeric"
        aria-label="Page number"
        value={text}
        onFocus={(e) => { editing.current = true; e.currentTarget.select(); }}
        onInput={(e) => setText(e.currentTarget.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") { e.currentTarget.blur(); } if (e.key === "Escape") { setText(String(page + 1)); e.currentTarget.blur(); } }}
      />
      <span>of {pages}</span>
    </label>
  );
}

function Bookmarks({ page, bookmarks, onBookmark, onGo }: Pick<ToolbarProps, "page" | "bookmarks" | "onBookmark" | "onGo">) {
  const marked = bookmarks.includes(page);
  const label = marked ? "Remove the bookmark on this page" : "Bookmark this page";
  const target = nextBookmark(bookmarks, page);
  return (
    <>
      <button type="button" class={marked ? "icon-btn on" : "icon-btn"} aria-pressed={marked} aria-label={label} title={`${label} (B)`} onClick={onBookmark}>
        <Bookmark size={18} fill={marked ? "currentColor" : "none"} />
      </button>
      {target === null ? null : (
        <button type="button" class="btn small rd-gomark" title={`Go to your bookmark on page ${target + 1} (Shift+B)`} onClick={() => onGo(target)}>
          <Bookmark size={14} fill="currentColor" /> Page {target + 1}
        </button>
      )}
    </>
  );
}

function SearchBox(p: ToolbarProps) {
  const s = p.search;
  const count = s.status === "busy" ? "Searching" : s.status === "error" ? "Failed"
    : s.status === "done" ? (s.flat.length ? `${s.current + 1} of ${s.flat.length}` : "No matches") : "";
  const [text, setText] = useState("");
  const submit = (e: KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (text.trim() === s.query && s.flat.length) p.onStep(e.shiftKey ? -1 : 1);
      else p.onSearch(text);
    } else if (e.key === "Escape") {
      setText(""); p.onClear(); (e.currentTarget as HTMLElement).blur();
    }
  };
  return (
    <div class="rd-search" title={s.message || undefined}>
      <Search size={15} aria-hidden="true" />
      <input
        ref={p.searchBox as { current: HTMLInputElement | null }}
        dir="auto"
        type="text"
        placeholder="Search in this PDF"
        aria-label="Search in this PDF"
        value={text}
        onInput={(e) => { setText(e.currentTarget.value); if (!e.currentTarget.value) p.onClear(); }}
        onKeyDown={submit}
      />
      {count ? <span class="rd-count">{count}</span> : null}
      <button type="button" class="icon-btn" aria-label="Previous match" disabled={!s.flat.length} onClick={() => p.onStep(-1)}><ChevronUp size={16} /></button>
      <button type="button" class="icon-btn" aria-label="Next match" disabled={!s.flat.length} onClick={() => p.onStep(1)}><ChevronDown size={16} /></button>
      {text ? <button type="button" class="icon-btn" aria-label="Clear search" onClick={() => { setText(""); p.onClear(); }}><X size={15} /></button> : null}
    </div>
  );
}

export function Toolbar(p: ToolbarProps) {
  return (
    <header class="rd-bar">
      <a class="back" href="#/" onClick={p.onBack} title="All tools"><ArrowLeft size={16} /></a>
      <button type="button" class={p.sidebar ? "icon-btn on" : "icon-btn"} aria-pressed={p.sidebar} aria-label="Page thumbnails" title="Page thumbnails" onClick={p.onSidebar}><PanelLeft size={18} /></button>
      <FileName name={p.name} class="rd-name" />
      <i class="sep" />
      <PageBox page={p.page} pages={p.pages} onGo={p.onGo} />
      <Bookmarks page={p.page} bookmarks={p.bookmarks} onBookmark={p.onBookmark} onGo={p.onGo} />
      <div class="rd-zoom" role="group" aria-label="Zoom">
        <button type="button" class="icon-btn" aria-label="Zoom out" title="Zoom out (Ctrl and minus)" onClick={() => p.onZoom(-1)}><ZoomOut size={17} /></button>
        <span class="rd-pct">{p.zoomPct}%</span>
        <button type="button" class="icon-btn" aria-label="Zoom in" title="Zoom in (Ctrl and plus)" onClick={() => p.onZoom(1)}><ZoomIn size={17} /></button>
        <button type="button" class={p.fit ? "icon-btn on" : "icon-btn"} aria-pressed={p.fit} aria-label="Fit width" title="Fit width (Ctrl+0)" onClick={p.onFit}><MoveHorizontal size={17} /></button>
      </div>
      <SearchBox {...p} />
      <span class="grow" />
      <div class="rd-tools" role="toolbar" aria-label="Annotation tools">
        {TOOLS.map(({ id, label, key, Icon }) => (
          <button type="button" class={p.tool === id ? "icon-btn on" : "icon-btn"} aria-pressed={p.tool === id}
            aria-label={label} title={`${label} (${key})`} onClick={() => p.onTool(id)}><Icon size={18} /></button>
        ))}
      </div>
      <div class="rd-colors" role="radiogroup" aria-label="Colour">
        {COLORS.map((c) => (
          <button type="button" role="radio" aria-checked={p.color === c.value} aria-label={c.label} title={c.label}
            class={p.color === c.value ? "swatch on" : "swatch"} style={{ "--c": c.value }} onClick={() => p.onColor(c.value)} />
        ))}
      </div>
      <button type="button" class="icon-btn" disabled={!p.pending} aria-label="Undo last mark" title="Undo last mark (Ctrl+Z)" onClick={p.onUndo}><Undo2 size={18} /></button>
      <button type="button" class="btn small primary" disabled={!p.pending || p.saving} title="Save marks into a copy of this PDF (Ctrl+S)" onClick={p.onSave}>
        <Save size={15} /> {p.saving ? "Saving" : p.pending ? `Save ${p.pending}` : "Save"}
      </button>
      <button type="button" class="icon-btn" aria-label="Print" title="Print (Ctrl+P)" onClick={p.onPrint}><Printer size={18} /></button>
    </header>
  );
}
