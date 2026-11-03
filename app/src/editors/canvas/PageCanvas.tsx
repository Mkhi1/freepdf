import { useRef, useState } from "preact/hooks";
import type { ComponentChildren } from "preact";
import { boxFromCorners, clampPoint, clientToPage, imageWidthFor, moveBox, resizeBox } from "./geometry";
import type { Box, Handle, Pt } from "./geometry";
import type { DocView, DrawMode, Gesture, Item, PreviewStyle, Render } from "./types";
import { usePageUrl } from "./usePageUrl";
import "./canvas.css";

const BOX_HANDLES: Handle[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const CLICK_SLOP_PX = 4;

export interface PageCanvasProps<T extends Item> {
  doc: DocView;
  page: number;
  scale: number;
  items: readonly T[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  /** Called once before a drag changes anything, so the whole drag is one undo step. */
  onBegin: () => void;
  onChange: (next: T[]) => void;
  render: Render<T>;
  applyBox?: (item: T, box: Box) => T;
  applyEnd?: (item: T, index: 0 | 1, pt: Pt) => T;
  mode?: DrawMode;
  preview?: PreviewStyle;
  onDraw?: (gesture: Gesture) => void;
  onItemDoubleClick?: (id: string) => void;
  /** Drawn under the items, in page pixels (for example search hits). */
  underlay?: (scale: number) => ComponentChildren;
  cursor?: string;
  /** Pressing on an item selects it even while a draw mode is on. */
  itemsFirst?: boolean;
}

type Drag =
  | { kind: "move"; id: string; from: Pt; box: Box; began: boolean }
  | { kind: "resize"; id: string; handle: Handle; from: Pt; box: Box; began: boolean }
  | { kind: "end"; id: string; index: 0 | 1; began: boolean }
  | { kind: "draw"; from: Pt; points: Pt[]; startClient: Pt };

interface Draft { shape: "rect" | "line" | "ellipse" | "stroke"; a: Pt; b: Pt; points: Pt[] }

function handlesFor(item: Item): Handle[] {
  if (item.handles === "none" || item.handles === "ends") return [];
  if (item.handles === "x") return ["e", "w"];
  return item.keepAspect ? ["nw", "ne", "se", "sw"] : BOX_HANDLES;
}

export function PageCanvas<T extends Item>(props: PageCanvasProps<T>) {
  const { doc, page, scale, items, selectedId, mode = "none" } = props;
  const size = doc.sizes[page] ?? { w: 595, h: 842 };
  const pxW = size.w * scale;
  const pxH = size.h * scale;
  const overlay = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const image = usePageUrl(doc.file, page, imageWidthFor(size.w, scale, window.devicePixelRatio || 1), doc.password);
  const here = items.filter((i) => i.page === page);

  const pointOf = (e: PointerEvent): Pt => {
    const rect = overlay.current!.getBoundingClientRect();
    return clientToPage({ x: e.clientX, y: e.clientY }, rect, scale);
  };
  const replace = (id: string, update: (item: T) => T) => props.onChange(items.map((i) => (i.id === id ? update(i) : i)));
  const find = (id: string) => items.find((i) => i.id === id);

  const onDown = (e: PointerEvent) => {
    const target = e.target as HTMLElement;
    if (e.button !== 0 || target.closest("textarea,input,select,button")) return;
    const at = pointOf(e);
    const handleEl = target.closest<HTMLElement>("[data-handle]");
    const itemEl = target.closest<HTMLElement>("[data-item]");
    const selected = selectedId ? find(selectedId) : undefined;
    if (handleEl && selected) {
      const name = handleEl.dataset.handle!;
      drag.current = name === "p0" || name === "p1"
        ? { kind: "end", id: selected.id, index: name === "p0" ? 0 : 1, began: false }
        : { kind: "resize", id: selected.id, handle: name as Handle, from: at, box: selected.box, began: false };
    } else if (mode === "none" || (props.itemsFirst && itemEl)) {
      const id = itemEl?.dataset.item ?? null;
      props.onSelect(id);
      const hit = id ? find(id) : undefined;
      if (!hit) return;
      drag.current = { kind: "move", id: hit.id, from: at, box: hit.box, began: false };
    } else {
      props.onSelect(null);
      drag.current = { kind: "draw", from: clampPoint(at, size), points: [clampPoint(at, size)], startClient: { x: e.clientX, y: e.clientY } };
      setDraft({ shape: mode === "stroke" || mode === "point" ? "stroke" : mode, a: at, b: at, points: [at] });
    }
    overlay.current!.setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  const begin = (d: { began: boolean }) => {
    if (!d.began) { d.began = true; props.onBegin(); }
  };

  const onMove = (e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const at = pointOf(e);
    if (d.kind === "draw") {
      const p = clampPoint(at, size);
      const points = mode === "stroke" ? [...d.points, p] : d.points;
      if (mode === "stroke") d.points = points;
      setDraft((cur) => (cur ? { ...cur, a: d.from, b: p, points } : cur));
      return;
    }
    const target = find(d.id);
    if (!target) return;
    const delta = { x: at.x - (d.kind === "end" ? 0 : d.from.x), y: at.y - (d.kind === "end" ? 0 : d.from.y) };
    if (d.kind === "end") {
      begin(d);
      replace(d.id, (i) => (props.applyEnd ? props.applyEnd(i, d.index, clampPoint(at, size)) : i));
      return;
    }
    if (!d.began && Math.hypot(delta.x, delta.y) * scale < 2) return;
    begin(d);
    const next = d.kind === "move"
      ? moveBox(d.box, delta, size)
      : resizeBox(d.box, d.handle, delta, { min: target.minSize ?? 6, page: size, keepAspect: target.keepAspect });
    replace(d.id, (i) => (props.applyBox ? props.applyBox(i, next) : { ...i, box: next }));
  };

  const finishDraw = (d: Extract<Drag, { kind: "draw" }>, e: PointerEvent) => {
    const end = clampPoint(pointOf(e), size);
    const moved = Math.hypot(e.clientX - d.startClient.x, e.clientY - d.startClient.y);
    if (mode === "point" || moved < CLICK_SLOP_PX) {
      props.onDraw?.({ type: "click", page, pt: d.from });
    } else if (mode === "stroke") {
      props.onDraw?.({ type: "stroke", page, points: [...d.points, end] });
    } else {
      props.onDraw?.({ type: "rect", page, box: boxFromCorners(d.from, end), start: d.from, end });
    }
  };

  const onUp = (e: PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    setDraft(null);
    if (d?.kind === "draw") finishDraw(d, e);
  };

  const cursor = props.cursor ?? (mode === "none" ? "default" : "crosshair");
  return (
    <div class="ed-page" style={{ width: `${pxW}px`, height: `${pxH}px` }}>
      {image.url ? <img class="ed-bg" src={image.url} alt={`Page ${page + 1}`} draggable={false} /> : <span class="ed-wait" />}
      {image.failed && !image.url ? <span class="ed-fail">No preview for this page</span> : null}
      <div
        ref={overlay}
        class="ed-overlay"
        style={{ cursor }}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
      >
        {props.underlay?.(scale)}
        {here.map((item) => (
          <ItemView
            key={item.id}
            item={item}
            scale={scale}
            selected={item.id === selectedId}
            interactive={mode === "none" || !!props.itemsFirst}
            onDoubleClick={props.onItemDoubleClick}
          >
            {props.render(item, { scale, selected: item.id === selectedId })}
          </ItemView>
        ))}
        {draft ? <DraftView draft={draft} scale={scale} style={props.preview} /> : null}
      </div>
    </div>
  );
}

interface ItemViewProps {
  item: Item;
  scale: number;
  selected: boolean;
  interactive: boolean;
  onDoubleClick?: (id: string) => void;
  children: ComponentChildren;
}

function ItemView({ item, scale, selected, interactive, onDoubleClick, children }: ItemViewProps) {
  const b = item.box;
  const style: Record<string, string> = {
    left: `${b.x * scale}px`, top: `${b.y * scale}px`, width: `${b.w * scale}px`,
    height: item.autoHeight ? "auto" : `${b.h * scale}px`,
  };
  if (item.autoHeight) style.minHeight = `${b.h * scale}px`;
  return (
    <div
      class={`ed-item${selected ? " sel" : ""}${interactive ? "" : " passive"}`}
      data-item={item.id}
      style={style}
      onDblClick={() => onDoubleClick?.(item.id)}
    >
      {children}
      {selected ? <Frame item={item} scale={scale} /> : null}
    </div>
  );
}

function Frame({ item, scale }: { item: Item; scale: number }) {
  if (item.handles === "ends" && item.ends) {
    const origin = item.box;
    return (
      <>
        {item.ends.map((p, i) => (
          <i
            class="ed-h end"
            data-handle={`p${i}`}
            style={{ left: `${(p.x - origin.x) * scale}px`, top: `${(p.y - origin.y) * scale}px` }}
          />
        ))}
      </>
    );
  }
  return (
    <>
      <span class="ed-ring" />
      {handlesFor(item).map((h) => <i class={`ed-h ${h}`} data-handle={h} />)}
    </>
  );
}

function DraftView({ draft, scale, style }: { draft: Draft; scale: number; style?: PreviewStyle }) {
  const stroke = style?.stroke ?? "var(--accent)";
  const width = Math.max((style?.width ?? 1.5) * scale, 1.5);
  if (draft.shape === "stroke") {
    const d = draft.points.map((p, i) => `${i ? "L" : "M"}${p.x * scale} ${p.y * scale}`).join(" ");
    return (
      <svg class="ed-draft">
        <path d={d} fill="none" stroke={stroke} stroke-width={width} stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    );
  }
  if (draft.shape === "line") {
    return (
      <svg class="ed-draft">
        <line x1={draft.a.x * scale} y1={draft.a.y * scale} x2={draft.b.x * scale} y2={draft.b.y * scale}
          stroke={stroke} stroke-width={width} stroke-linecap="round" />
      </svg>
    );
  }
  const box = boxFromCorners(draft.a, draft.b);
  const round = draft.shape === "ellipse" ? "50%" : "0";
  return (
    <div
      class="ed-rubber"
      style={{
        left: `${box.x * scale}px`, top: `${box.y * scale}px`, width: `${box.w * scale}px`, height: `${box.h * scale}px`,
        borderRadius: round, background: style?.fill ?? "color-mix(in srgb, var(--accent) 14%, transparent)",
        borderColor: style?.stroke ?? "var(--accent)",
      }}
    />
  );
}
