import type { ComponentChildren } from "preact";
import { useEffect, useRef } from "preact/hooks";
import type { Box, Pt } from "./geometry";

export const CSS_FONTS: Record<string, string> = {
  Arial: "Arial, Helvetica, sans-serif",
  Times: '"Times New Roman", Times, serif',
  Courier: '"Courier New", Courier, monospace',
  "Segoe UI": '"Segoe UI", system-ui, sans-serif',
  Tahoma: "Tahoma, sans-serif",
  Verdana: "Verdana, sans-serif",
  Calibri: "Calibri, Carlito, sans-serif",
};

export interface TextStyle {
  text: string;
  font: string;
  size: number;
  color: string;
  bold: boolean;
  italic: boolean;
}

/** Text on the page. Double click (or editing = true) turns it into a text box. */
export function TextBlock(props: {
  style: TextStyle;
  scale: number;
  editing: boolean;
  onText: (text: string) => void;
  onFocus: () => void;
  onDone: () => void;
}) {
  const s = props.style;
  const area = useRef<HTMLTextAreaElement>(null);
  const css = {
    fontFamily: CSS_FONTS[s.font] ?? CSS_FONTS.Arial,
    fontSize: `${s.size * props.scale}px`,
    color: s.color,
    fontWeight: s.bold ? "700" : "400",
    fontStyle: s.italic ? "italic" : "normal",
  };
  useEffect(() => {
    if (props.editing) { area.current?.focus(); area.current?.select(); }
  }, [props.editing]);
  if (props.editing) {
    return (
      <textarea
        ref={area}
        class="ed-text-input"
        dir="auto"
        style={css}
        value={s.text}
        onFocus={props.onFocus}
        onInput={(e) => props.onText(e.currentTarget.value)}
        onBlur={props.onDone}
        onKeyDown={(e) => { if (e.key === "Escape") props.onDone(); }}
      />
    );
  }
  return <div class="ed-text" dir="auto" style={{ ...css, position: "relative" }}>{s.text || " "}</div>;
}

/** Vector layer for one item: its viewBox is the item's box in points, so drawings use page units. */
export function ItemSvg({ box, children }: { box: Box; children: ComponentChildren }) {
  return (
    <svg class="ed-svg" viewBox={`${box.x} ${box.y} ${Math.max(box.w, 0.01)} ${Math.max(box.h, 0.01)}`} preserveAspectRatio="none">
      {children}
    </svg>
  );
}

export function pathOf(points: readonly Pt[]): string {
  return points.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(" ");
}

/** Midpoint-smoothed path, close to how the engine curves ink. */
export function smoothPath(points: readonly Pt[]): string {
  if (points.length < 3) return pathOf(points);
  let d = `M${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const mid = { x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2 };
    d += ` Q${points[i].x.toFixed(2)} ${points[i].y.toFixed(2)} ${mid.x.toFixed(2)} ${mid.y.toFixed(2)}`;
  }
  const last = points[points.length - 1];
  return `${d} L${last.x.toFixed(2)} ${last.y.toFixed(2)}`;
}

/** Thins a stroke so the engine call stays small. */
export function thin(points: readonly Pt[], minGap = 1): Pt[] {
  const out: Pt[] = [];
  for (const p of points) {
    const prev = out[out.length - 1];
    if (!prev || Math.hypot(p.x - prev.x, p.y - prev.y) >= minGap) out.push(p);
  }
  const last = points[points.length - 1];
  if (last && out[out.length - 1] !== last) out.push(last);
  return out;
}
