import { boundsOf, round2, toRect } from "../canvas/geometry";
import type { Pt } from "../canvas/geometry";
import type { Item } from "../canvas/types";
import { thin } from "../canvas/ItemViews";
import { imageSrc } from "../kit";

/** A saved signature: a picture file, or pen strokes kept as vectors (so the background is always clear). */
export type SigAsset =
  | { id: string; kind: "image"; label: string; path: string; aspect: number }
  | { id: string; kind: "drawn"; label: string; strokes: Pt[][]; width: number; color: string; aspect: number; w: number; h: number };

interface SignatureData { kind: "signature"; asset: SigAsset }
interface FieldData { kind: "field"; text: string; font: string; size: number; color: string; bold: boolean; italic: boolean }
export type SignItem = Item & (SignatureData | FieldData);

export const PAD_W = 420;
export const PAD_H = 170;
export const PEN_WIDTH = 3;
const STORE_KEY = "freepdf.signatures.v1";

export function loadAssets(): SigAsset[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as SigAsset[]) : [];
  } catch {
    return [];
  }
}

export function saveAssets(assets: readonly SigAsset[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(assets.slice(-8)));
  } catch {
    /* storage can be off; signatures then last for this session only */
  }
}

/** Crops strokes to the ink so the signature scales cleanly. */
export function drawnAsset(id: string, strokes: readonly Pt[][], color: string): SigAsset | null {
  const all = strokes.flat();
  if (all.length < 2) return null;
  const box = boundsOf(all, PEN_WIDTH);
  const moved = strokes.map((s) => thin(s, 0.8).map((p) => ({ x: round2(p.x - box.x), y: round2(p.y - box.y) })));
  return { id, kind: "drawn", label: "Drawn", strokes: moved, width: PEN_WIDTH, color, aspect: box.w / box.h, w: box.w, h: box.h };
}

export function imageAspect(path: string): Promise<number> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 3);
    img.onerror = () => resolve(3);
    img.src = imageSrc(path);
  });
}

export function signatureItem(id: string, page: number, asset: SigAsset, at: Pt, width = 150): SignItem {
  const h = width / asset.aspect;
  return { id, page, kind: "signature", asset, box: { x: at.x - width / 2, y: at.y - h / 2, w: width, h }, keepAspect: true };
}

export function fieldItem(id: string, page: number, text: string, at: Pt, size: number): SignItem {
  return {
    id, page, kind: "field", text, font: "Arial", size, color: "#111111", bold: false, italic: false,
    box: { x: at.x, y: at.y, w: Math.max(80, text.length * size * 0.6), h: size * 1.25 }, handles: "x", autoHeight: true,
  };
}

function fieldArgs(item: Extract<SignItem, { kind: "field" }>) {
  return {
    page: item.page, x: round2(item.box.x), y: round2(item.box.y), text: item.text, font: item.font, size: item.size,
    color: item.color, bold: item.bold, italic: item.italic, width: round2(item.box.w),
  };
}

function inkArgs(item: Extract<SignItem, { kind: "signature" }>, asset: Extract<SigAsset, { kind: "drawn" }>) {
  const k = item.box.w / asset.w;
  return asset.strokes.map((stroke) => ({
    type: "ink", page: item.page, color: asset.color, width: round2(asset.width * k),
    points: stroke.map((p) => [round2(item.box.x + p.x * k), round2(item.box.y + p.y * k)]),
  }));
}

export interface SignPlan { tool: "sign"; args: Record<string, unknown> }

export function buildSignPlan(file: string, password: string | undefined, items: readonly SignItem[]): SignPlan {
  const base = { file, ...(password ? { password } : {}) };
  const list: Record<string, unknown>[] = [];
  for (const item of items) {
    if (item.kind === "field") {
      if (item.text.trim()) list.push({ type: "text_field", ...fieldArgs(item) });
    } else if (item.asset.kind === "drawn") {
      list.push(...inkArgs(item, item.asset));
    } else {
      list.push({ type: "signature", page: item.page, rect: toRect(item.box), image_path: item.asset.path });
    }
  }
  return { tool: "sign", args: { ...base, items: list } };
}
