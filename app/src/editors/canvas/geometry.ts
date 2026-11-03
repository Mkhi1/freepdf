// All screen <-> PDF point maths for the page canvas lives here, so it can be tested on its own.
// Page space: PDF points, origin at the top left of the page as the viewer shows it (rotation applied).

export interface Pt { x: number; y: number }
export interface Size { w: number; h: number }
export interface Box { x: number; y: number; w: number; h: number }
export type Rotation = 0 | 90 | 180 | 270;
export type Handle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

/** CSS pixels per PDF point at 100% zoom. */
export const PX_PER_PT = 96 / 72;
export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 4;

export function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

export function normalizeRotation(degrees: number): Rotation {
  return ((((Math.round(degrees / 90) * 90) % 360) + 360) % 360) as Rotation;
}

/** Size of a page as the viewer shows it, from its stored (unrotated) size. */
export function visualSize(raw: Size, rotation: number): Size {
  const turned = normalizeRotation(rotation) % 180 !== 0;
  return turned ? { w: raw.h, h: raw.w } : { w: raw.w, h: raw.h };
}

/** Point on the unrotated page to the same spot as the viewer shows it (rotation is clockwise). */
export function toVisual(pt: Pt, raw: Size, rotation: number): Pt {
  switch (normalizeRotation(rotation)) {
    case 90: return { x: raw.h - pt.y, y: pt.x };
    case 180: return { x: raw.w - pt.x, y: raw.h - pt.y };
    case 270: return { x: pt.y, y: raw.w - pt.x };
    default: return { x: pt.x, y: pt.y };
  }
}

/** Inverse of toVisual. */
export function fromVisual(pt: Pt, raw: Size, rotation: number): Pt {
  switch (normalizeRotation(rotation)) {
    case 90: return { x: pt.y, y: raw.h - pt.x };
    case 180: return { x: raw.w - pt.x, y: raw.h - pt.y };
    case 270: return { x: raw.w - pt.y, y: pt.x };
    default: return { x: pt.x, y: pt.y };
  }
}

export function ptToPx(value: number, scale: number): number {
  return value * scale;
}

export function pxToPt(value: number, scale: number): number {
  return value / scale;
}

/** Pointer position (client pixels) to a point on the page. `origin` is the page element's client rect. */
export function clientToPage(client: Pt, origin: { left: number; top: number }, scale: number): Pt {
  return { x: (client.x - origin.left) / scale, y: (client.y - origin.top) / scale };
}

export function pageToClient(pt: Pt, origin: { left: number; top: number }, scale: number): Pt {
  return { x: origin.left + pt.x * scale, y: origin.top + pt.y * scale };
}

export function boxToPx(box: Box, scale: number): Box {
  return { x: box.x * scale, y: box.y * scale, w: box.w * scale, h: box.h * scale };
}

export function boxFromCorners(a: Pt, b: Pt): Box {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) };
}

export function clampPoint(pt: Pt, page: Size): Pt {
  return { x: clamp(pt.x, 0, page.w), y: clamp(pt.y, 0, page.h) };
}

/** Moves a box inside the page without changing its size (it shrinks only when larger than the page). */
export function fitInside(box: Box, page: Size): Box {
  const w = Math.min(box.w, page.w);
  const h = Math.min(box.h, page.h);
  return { x: clamp(box.x, 0, page.w - w), y: clamp(box.y, 0, page.h - h), w, h };
}

export function moveBox(box: Box, delta: Pt, page: Size): Box {
  return fitInside({ ...box, x: box.x + delta.x, y: box.y + delta.y }, page);
}

export interface ResizeOptions {
  min: number;
  page?: Size;
  keepAspect?: boolean;
}

function edges(box: Box) {
  return { x0: box.x, y0: box.y, x1: box.x + box.w, y1: box.y + box.h };
}

function resizeFree(start: Box, handle: Handle, d: Pt, o: ResizeOptions): Box {
  const e = edges(start);
  if (handle.includes("w")) e.x0 += d.x;
  if (handle.includes("e")) e.x1 += d.x;
  if (handle.includes("n")) e.y0 += d.y;
  if (handle.includes("s")) e.y1 += d.y;
  const hi = o.page ?? { w: Infinity, h: Infinity };
  e.x0 = clamp(e.x0, 0, hi.w);
  e.x1 = clamp(e.x1, 0, hi.w);
  e.y0 = clamp(e.y0, 0, hi.h);
  e.y1 = clamp(e.y1, 0, hi.h);
  if (e.x1 - e.x0 < o.min) {
    if (handle.includes("w")) e.x0 = e.x1 - o.min;
    else e.x1 = e.x0 + o.min;
  }
  if (e.y1 - e.y0 < o.min) {
    if (handle.includes("n")) e.y0 = e.y1 - o.min;
    else e.y1 = e.y0 + o.min;
  }
  return { x: e.x0, y: e.y0, w: e.x1 - e.x0, h: e.y1 - e.y0 };
}

function resizeKeepingAspect(start: Box, handle: Handle, d: Pt, o: ResizeOptions): Box {
  const west = handle.includes("w");
  const north = handle.includes("n");
  const anchor = { x: west ? start.x + start.w : start.x, y: north ? start.y + start.h : start.y };
  const wanted = { w: start.w + (west ? -d.x : d.x), h: start.h + (north ? -d.y : d.y) };
  let factor = Math.max(wanted.w / start.w, wanted.h / start.h);
  const room = o.page ?? { w: Infinity, h: Infinity };
  factor = Math.min(factor, (west ? anchor.x : room.w - anchor.x) / start.w, (north ? anchor.y : room.h - anchor.y) / start.h);
  factor = Math.max(factor, o.min / Math.min(start.w, start.h));
  const w = start.w * factor;
  const h = start.h * factor;
  return { x: west ? anchor.x - w : anchor.x, y: north ? anchor.y - h : anchor.y, w, h };
}

/** New box when a handle is dragged by `delta` (page points) from the box as it was at pointer down. */
export function resizeBox(start: Box, handle: Handle, delta: Pt, options: ResizeOptions): Box {
  const corner = handle.length === 2;
  if (options.keepAspect && corner && start.w > 0 && start.h > 0) return resizeKeepingAspect(start, handle, delta, options);
  return resizeFree(start, handle, delta, options);
}

export function boundsOf(points: readonly Pt[], pad = 0): Box {
  if (!points.length) return { x: 0, y: 0, w: 1, h: 1 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = Math.min(...xs) - pad;
  const y = Math.min(...ys) - pad;
  return { x, y, w: Math.max(Math.max(...xs) + pad - x, 1), h: Math.max(Math.max(...ys) + pad - y, 1) };
}

/** Carries a point from one box into another, the way resizing a drawing stretches it. */
export function remapPoint(pt: Pt, from: Box, to: Box): Pt {
  const u = from.w > 0 ? (pt.x - from.x) / from.w : 0;
  const v = from.h > 0 ? (pt.y - from.y) / from.h : 0;
  return { x: to.x + u * to.w, y: to.y + v * to.h };
}

export function remapPoints(points: readonly Pt[], from: Box, to: Box): Pt[] {
  return points.map((p) => remapPoint(p, from, to));
}

/** The [x0, y0, x1, y1] list the engine wants for a rectangle. */
export function toRect(box: Box): [number, number, number, number] {
  return [round2(box.x), round2(box.y), round2(box.x + box.w), round2(box.y + box.h)];
}

export function fromRect(rect: readonly number[]): Box {
  const [x0, y0, x1, y1] = rect;
  return { x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0), h: Math.abs(y1 - y0) };
}

export function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function zoomToScale(zoom: number): number {
  return zoom * PX_PER_PT;
}

export function scaleToZoom(scale: number): number {
  return scale / PX_PER_PT;
}

/** Scale that makes a page of `pageWidth` points fill `available` pixels. */
export function fitWidthScale(available: number, pageWidth: number): number {
  return clamp(available / pageWidth, MIN_ZOOM * PX_PER_PT, MAX_ZOOM * PX_PER_PT);
}

const ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.25, 1.5, 2, 3, 4];

/** Next zoom stop above or below the current zoom. */
export function stepZoom(zoom: number, direction: 1 | -1): number {
  if (direction > 0) return ZOOM_STEPS.find((s) => s > zoom + 0.01) ?? MAX_ZOOM;
  return [...ZOOM_STEPS].reverse().find((s) => s < zoom - 0.01) ?? MIN_ZOOM;
}

/** Pixel width to ask the viewer for, rounded up so nearby zooms share cached pictures. */
export function imageWidthFor(pageWidthPt: number, scale: number, dpr: number): number {
  const wanted = pageWidthPt * scale * clamp(dpr, 1, 2);
  return clamp(Math.ceil(wanted / 160) * 160, 320, 3200);
}
