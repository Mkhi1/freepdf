import { FileImage } from "lucide-preact";
import { useState } from "preact/hooks";
import { imageSrc } from "../kit";
import { ItemSvg, TextBlock, smoothPath } from "../canvas/ItemViews";
import type { Pt } from "../canvas/geometry";
import type { RenderContext } from "../canvas/types";
import type { EditItem } from "./items";

export interface ViewHooks {
  editingId: string | null;
  onText: (id: string, text: string) => void;
  onEditStart: () => void;
  onEditDone: (id: string) => void;
}

export function arrowHead(a: Pt, b: Pt, width: number): string {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const size = Math.max(width * 4, 10);
  const back = { x: b.x - ux * size, y: b.y - uy * size };
  const nx = -uy * size * 0.45;
  const ny = ux * size * 0.45;
  return `${back.x + nx},${back.y + ny} ${b.x},${b.y} ${back.x - nx},${back.y - ny}`;
}

function PictureView({ path }: { path: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) {
    return <div class="ed-note" style={{ background: "var(--surface-2)", color: "var(--muted)", boxShadow: "0 0 0 1px var(--line)" }}><FileImage size={28} /></div>;
  }
  return <img src={imageSrc(path)} alt="" draggable={false} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} onError={() => setBroken(true)} />;
}

function ShapeView({ item }: { item: Extract<EditItem, { kind: "shape" }> }) {
  const b = item.box;
  const common = { stroke: item.stroke, "stroke-width": item.width, fill: item.fill || "none", "stroke-linecap": "round" as const };
  let body;
  if (item.shape === "ellipse") {
    body = <ellipse cx={b.x + b.w / 2} cy={b.y + b.h / 2} rx={b.w / 2} ry={b.h / 2} {...common} />;
  } else if (item.shape === "rect") {
    body = <rect x={b.x} y={b.y} width={b.w} height={b.h} {...common} />;
  } else {
    const [p, q] = item.ends ?? [{ x: b.x, y: b.y }, { x: b.x + b.w, y: b.y + b.h }];
    body = (
      <>
        <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} {...common} fill="none" />
        {item.shape === "arrow" ? <polygon points={arrowHead(p, q, item.width)} fill={item.stroke} stroke={item.stroke} stroke-width={1} stroke-linejoin="miter" /> : null}
      </>
    );
  }
  return <ItemSvg box={b}>{body}</ItemSvg>;
}

export function renderEditItem(item: EditItem, ctx: RenderContext, hooks: ViewHooks) {
  switch (item.kind) {
    case "text":
      return (
        <TextBlock
          style={item}
          scale={ctx.scale}
          editing={hooks.editingId === item.id}
          onText={(text) => hooks.onText(item.id, text)}
          onFocus={hooks.onEditStart}
          onDone={() => hooks.onEditDone(item.id)}
        />
      );
    case "image":
      return <PictureView path={item.path} />;
    case "shape":
      return <ShapeView item={item} />;
    case "ink":
      return (
        <ItemSvg box={item.box}>
          <path d={smoothPath(item.points)} fill="none" stroke={item.color} stroke-width={item.width} stroke-linecap="round" stroke-linejoin="round" />
        </ItemSvg>
      );
    case "whiteout":
      return <div style={{ position: "absolute", inset: 0, background: item.color, boxShadow: ctx.selected ? "none" : "inset 0 0 0 1px rgba(0,0,0,.06)" }} />;
  }
}
