import { useEffect, useRef, useState } from "preact/hooks";
import { cached, loadPage } from "./loader";
import { normalize } from "./annots";
import type { Annot, Rect, Tool } from "./annots";
import { boxStyle, pathOf, Shapes } from "./Shapes";
import type { Size } from "./Shapes";
import { NotePopover } from "./NotePopover";

export interface PageLayerProps {
  file: string;
  password?: string;
  page: number;
  size: Size;
  /** CSS pixels per PDF point. */
  scale: number;
  /** Pixel width to ask the engine for. */
  imageWidth: number;
  /** How far this page is from what the reader is looking at. */
  distance: () => number;
  tool: Tool;
  color: string;
  bookmarked: boolean;
  annots: readonly Annot[];
  selected: number | null;
  editing: number | null;
  hits: readonly Rect[];
  currentHit: number | null;
  onAdd: (draft: Omit<Annot, "id">) => void;
  onPick: (annot: Annot) => void;
  onNoteText: (id: number, text: string | null) => void;
}

interface Draft { kind: "box" | "pen"; start: [number, number]; box?: Rect; points?: Array<[number, number]> }

export function PageLayer(p: PageLayerProps) {
  const host = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | undefined>(() => cached(p.file, p.page, p.imageWidth));
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  useEffect(() => {
    const hit = cached(p.file, p.page, p.imageWidth);
    if (hit) { setSrc(hit); return; }
    let alive = true;
    void loadPage({
      file: p.file, page: p.page, width: p.imageWidth, password: p.password,
      priority: p.distance, wanted: () => alive,
    }).then((url) => {
      if (!alive) return;
      if (url) { setSrc(url); setFailed(false); } else if (!src) setFailed(true);
    });
    return () => { alive = false; };
  }, [p.file, p.page, p.imageWidth, p.password]);

  const point = (e: PointerEvent): [number, number] => {
    const r = host.current!.getBoundingClientRect();
    return [Math.max(0, Math.min(p.size[0], (e.clientX - r.left) / p.scale)), Math.max(0, Math.min(p.size[1], (e.clientY - r.top) / p.scale))];
  };
  const drawing = p.tool !== "select";

  const down = (e: PointerEvent) => {
    if (!drawing || e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const at = point(e);
    if (p.tool === "note") {
      p.onAdd({ type: "note", page: p.page, color: p.color, x: at[0], y: at[1], text: "" });
      return;
    }
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDraft(p.tool === "pen" ? { kind: "pen", start: at, points: [at] } : { kind: "box", start: at, box: normalize(at, at) });
  };
  const move = (e: PointerEvent) => {
    if (!draft) return;
    const at = point(e);
    if (draft.kind === "box") setDraft({ ...draft, box: normalize(draft.start, at) });
    else {
      const last = draft.points![draft.points!.length - 1];
      if (Math.hypot(at[0] - last[0], at[1] - last[1]) >= 1) setDraft({ ...draft, points: [...draft.points!, at] });
    }
  };
  const up = () => {
    if (!draft) return;
    if (draft.kind === "pen" && (draft.points?.length ?? 0) > 1) {
      p.onAdd({ type: "ink", page: p.page, color: p.color, points: draft.points });
    } else if (draft.kind === "box" && draft.box && draft.box[2] - draft.box[0] > 3 && draft.box[3] - draft.box[1] > 3) {
      p.onAdd({ type: p.tool === "underline" ? "underline" : "highlight", page: p.page, color: p.color, rect: draft.box });
    }
    setDraft(null);
  };

  const addFromHit = (rect: Rect) => (e: Event) => {
    if (p.tool !== "highlight" && p.tool !== "underline") return;
    e.stopPropagation();
    p.onAdd({ type: p.tool, page: p.page, color: p.color, rect });
  };
  const clickable = p.tool === "highlight" || p.tool === "underline";
  const editingNote = p.annots.find((a) => a.id === p.editing && a.type === "note");

  return (
    <div
      ref={host}
      class={`rd-page${drawing ? " drawing" : ""} tool-${p.tool}`}
      style={{ width: `${p.size[0] * p.scale}px`, height: `${p.size[1] * p.scale}px` }}
      data-page={p.page}
    >
      {src ? <img src={src} alt={`Page ${p.page + 1}`} draggable={false} /> : null}
      {!src && !failed ? <span class="pageimg-wait" /> : null}
      {failed ? <span class="pageimg-fail">This page could not be drawn</span> : null}
      {p.bookmarked ? <i class="rd-ribbon" title="Bookmarked page" /> : null}
      {p.hits.map((rect, i) => (
        <i
          key={i}
          class={`hit${p.currentHit === i ? " now" : ""}${clickable ? " pick" : ""}`}
          style={boxStyle(rect, p.size)}
          onPointerDown={clickable ? addFromHit(rect) : undefined}
        />
      ))}
      <Shapes annots={p.annots} size={p.size} selected={p.selected} onPick={p.onPick} />
      {draft?.kind === "box" && draft.box ? (
        <div class={`ann ann-${p.tool === "underline" ? "underline" : "highlight"} draft`} style={{ ...boxStyle(draft.box, p.size), "--c": p.color }} />
      ) : null}
      {draft?.kind === "pen" ? (
        <svg class="ann-ink" viewBox={`0 0 ${p.size[0]} ${p.size[1]}`} preserveAspectRatio="none" aria-hidden="true">
          <path d={pathOf(draft.points ?? [])} stroke={p.color} stroke-width="2" />
        </svg>
      ) : null}
      {drawing ? <div class="rd-catch" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={() => setDraft(null)} /> : null}
      {editingNote ? <NotePopover note={editingNote} size={p.size} onText={p.onNoteText} /> : null}
    </div>
  );
}
