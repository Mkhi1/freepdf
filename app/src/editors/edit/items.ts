import { boundsOf, remapPoints, round2, toRect } from "../canvas/geometry";
import type { Box, Pt } from "../canvas/geometry";
import type { Item } from "../canvas/types";
import { thin } from "../canvas/ItemViews";

export type ShapeKind = "rect" | "ellipse" | "line" | "arrow";

interface TextData { kind: "text"; text: string; font: string; size: number; color: string; bold: boolean; italic: boolean }
interface ImageData { kind: "image"; path: string; aspect: number }
interface ShapeData { kind: "shape"; shape: ShapeKind; stroke: string; fill: string; width: number }
interface InkData { kind: "ink"; points: Pt[]; color: string; width: number }
interface WhiteoutData { kind: "whiteout"; color: string }

export type EditItem = Item & (TextData | ImageData | ShapeData | InkData | WhiteoutData);

export interface EditStyle {
  font: string; size: number; color: string; bold: boolean; italic: boolean;
  stroke: string; fillOn: boolean; fill: string; width: number; whiteout: string;
}

export const DEFAULT_STYLE: EditStyle = {
  font: "Arial", size: 18, color: "#111111", bold: false, italic: false,
  stroke: "#d32f2f", fillOn: false, fill: "#ffe082", width: 2, whiteout: "#ffffff",
};

export const INK_COLOR = "#1d4ed8";

/** Text boxes start at a readable width and grow taller by themselves. */
export function textItem(id: string, page: number, at: Pt, box: Box | null, style: EditStyle): EditItem {
  const w = box && box.w > 30 ? box.w : 220;
  return {
    id, page, kind: "text", text: "", font: style.font, size: style.size, color: style.color, bold: style.bold, italic: style.italic,
    box: { x: at.x, y: at.y, w, h: style.size * 1.25 }, handles: "x", autoHeight: true,
  };
}

export function imageItem(id: string, page: number, path: string, aspect: number, box: Box | null, at: Pt): EditItem {
  const w = box && box.w > 12 ? box.w : 180;
  const h = w / aspect;
  return { id, page, kind: "image", path, aspect, box: { x: box && box.w > 12 ? box.x : at.x, y: box && box.w > 12 ? box.y : at.y, w, h }, keepAspect: true };
}

export function shapeItem(id: string, page: number, shape: ShapeKind, start: Pt, end: Pt, style: EditStyle): EditItem {
  const common = { stroke: style.stroke, fill: style.fillOn ? style.fill : "", width: style.width };
  if (shape === "line" || shape === "arrow") {
    return { id, page, kind: "shape", shape, ...common, box: boundsOf([start, end]), ends: [start, end], handles: "ends" };
  }
  return { id, page, kind: "shape", shape, ...common, box: boundsOf([start, end]) };
}

export function inkItem(id: string, page: number, points: Pt[], style: EditStyle): EditItem {
  const kept = thin(points, 1.2);
  return { id, page, kind: "ink", points: kept, color: style.color, width: style.width, box: boundsOf(kept, style.width / 2) };
}

export function whiteoutItem(id: string, page: number, box: Box, style: EditStyle): EditItem {
  return { id, page, kind: "whiteout", color: style.whiteout, box };
}

export function applyBox(item: EditItem, box: Box): EditItem {
  if (item.kind === "ink") return { ...item, box, points: remapPoints(item.points, item.box, box) };
  if (item.kind === "shape" && item.ends) {
    const [a, b] = remapPoints(item.ends, item.box, box);
    return { ...item, box, ends: [a, b] };
  }
  return { ...item, box };
}

export function applyEnd(item: EditItem, index: 0 | 1, pt: Pt): EditItem {
  if (item.kind !== "shape" || !item.ends) return item;
  const ends: [Pt, Pt] = index === 0 ? [pt, item.ends[1]] : [item.ends[0], pt];
  return { ...item, ends, box: boundsOf(ends) };
}

/** Picks the style fields an item uses, so the sidebar can show them while it is selected. */
export function styleFrom(item: EditItem, base: EditStyle): EditStyle {
  switch (item.kind) {
    case "text": return { ...base, font: item.font, size: item.size, color: item.color, bold: item.bold, italic: item.italic };
    case "shape": return { ...base, stroke: item.stroke, fillOn: !!item.fill, fill: item.fill || base.fill, width: item.width };
    case "ink": return { ...base, color: item.color, width: item.width };
    case "whiteout": return { ...base, whiteout: item.color };
    default: return base;
  }
}

export function withStyle(item: EditItem, s: EditStyle): EditItem {
  switch (item.kind) {
    case "text": return { ...item, font: s.font, size: s.size, color: s.color, bold: s.bold, italic: s.italic };
    case "shape": return { ...item, stroke: s.stroke, fill: s.fillOn ? s.fill : "", width: s.width };
    case "ink": return { ...item, color: s.color, width: s.width, box: boundsOf(item.points, s.width / 2) };
    case "whiteout": return { ...item, color: s.whiteout };
    default: return item;
  }
}

export function toEngineItem(item: EditItem): Record<string, unknown> | null {
  const base = { page: item.page };
  switch (item.kind) {
    case "text":
      if (!item.text.trim()) return null;
      return {
        type: "text", ...base, x: round2(item.box.x), y: round2(item.box.y), text: item.text, font: item.font,
        size: item.size, color: item.color, bold: item.bold, italic: item.italic, width: round2(item.box.w),
      };
    case "image":
      return { type: "image", ...base, rect: toRect(item.box), path: item.path, rotate: 0 };
    case "shape": {
      const rect = item.ends ? [round2(item.ends[0].x), round2(item.ends[0].y), round2(item.ends[1].x), round2(item.ends[1].y)] : toRect(item.box);
      return { type: "shape", ...base, kind: item.shape, rect, stroke: item.stroke, fill: item.fill || null, width: item.width };
    }
    case "ink":
      return { type: "ink", ...base, points: item.points.map((p) => [round2(p.x), round2(p.y)]), color: item.color, width: item.width };
    case "whiteout":
      return { type: "whiteout", ...base, rect: toRect(item.box), color: item.color };
  }
}

export function buildEditArgs(file: string, password: string | undefined, items: readonly EditItem[]): Record<string, unknown> {
  const list = items.map(toEngineItem).filter((x): x is Record<string, unknown> => x !== null);
  return { file, ...(password ? { password } : {}), items: list };
}
