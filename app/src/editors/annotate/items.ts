import { boundsOf, remapPoints, round2, toRect } from "../canvas/geometry";
import type { Box, Pt } from "../canvas/geometry";
import type { Item } from "../canvas/types";
import { thin } from "../canvas/ItemViews";

export type MarkKind = "highlight" | "underline" | "strikeout";

interface MarkData { kind: MarkKind; color: string }
interface NoteData { kind: "note"; text: string; color: string }
interface InkData { kind: "ink"; points: Pt[]; color: string; width: number }
interface FreeData { kind: "freetext"; text: string; size: number; color: string }

export type NoteItem = Item & (MarkData | NoteData | InkData | FreeData);
export type AnnotKind = NoteItem["kind"];

export const DEFAULT_COLORS: Record<AnnotKind, string> = {
  highlight: "#ffe14d", underline: "#1565c0", strikeout: "#d32f2f", note: "#ffd600", ink: "#d32f2f", freetext: "#111111",
};

export function markItem(id: string, page: number, kind: MarkKind, box: Box, color: string): NoteItem {
  return { id, page, kind, color, box, minSize: 3 };
}

export function stickyItem(id: string, page: number, at: Pt, color: string): NoteItem {
  return { id, page, kind: "note", text: "", color, box: { x: at.x, y: at.y, w: 20, h: 20 }, handles: "none" };
}

export function inkAnnot(id: string, page: number, points: Pt[], color: string, width: number): NoteItem {
  const kept = thin(points, 1.2);
  return { id, page, kind: "ink", points: kept, color, width, box: boundsOf(kept, width / 2) };
}

export function freeItem(id: string, page: number, at: Pt, box: Box | null, color: string, size: number): NoteItem {
  const big = box && box.w > 30 && box.h > 12;
  return { id, page, kind: "freetext", text: "", size, color, box: big ? box : { x: at.x, y: at.y, w: 200, h: size * 2.4 } };
}

export function applyBox(item: NoteItem, box: Box): NoteItem {
  if (item.kind === "ink") return { ...item, box, points: remapPoints(item.points, item.box, box) };
  return { ...item, box };
}

export function withColor(item: NoteItem, color: string): NoteItem {
  return { ...item, color };
}

function toEngine(item: NoteItem): Record<string, unknown> | null {
  const base = { page: item.page };
  switch (item.kind) {
    case "highlight":
    case "underline":
    case "strikeout":
      return { type: item.kind, ...base, rect: toRect(item.box), color: item.color };
    case "note":
      return { type: "note", ...base, x: round2(item.box.x), y: round2(item.box.y), text: item.text, color: item.color };
    case "ink":
      return { type: "ink", ...base, points: item.points.map((p) => [round2(p.x), round2(p.y)]), color: item.color, width: item.width };
    case "freetext":
      if (!item.text.trim()) return null;
      return { type: "freetext", ...base, rect: toRect(item.box), text: item.text, size: item.size, color: item.color, font: "Arial" };
  }
}

export function buildAnnotateArgs(file: string, password: string | undefined, items: readonly NoteItem[]): Record<string, unknown> {
  const list = items.map(toEngine).filter((x): x is Record<string, unknown> => x !== null);
  return { file, ...(password ? { password } : {}), items: list };
}
