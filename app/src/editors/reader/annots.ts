export type Tool = "select" | "highlight" | "underline" | "note" | "pen";

export type Rect = [number, number, number, number];

export interface Annot {
  id: number;
  type: "highlight" | "underline" | "note" | "ink";
  /** 0-based page. */
  page: number;
  color: string;
  /** Highlight and underline: box in PDF points, origin top left. */
  rect?: Rect;
  /** Note: position in points. */
  x?: number;
  y?: number;
  text?: string;
  /** Pen: path in points. */
  points?: Array<[number, number]>;
}

export const COLORS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "#ffe14d", label: "Yellow" },
  { value: "#7ddc8a", label: "Green" },
  { value: "#7cc4ff", label: "Blue" },
  { value: "#ff9ec4", label: "Pink" },
  { value: "#e03131", label: "Red" },
  { value: "#212529", label: "Black" },
];

export const TOOL_COLOR: Record<Tool, string> = {
  select: "#ffe14d",
  highlight: "#ffe14d",
  underline: "#1c7ed6",
  note: "#ffe14d",
  pen: "#e03131",
};

let counter = 1;
export const newAnnotId = (): number => counter++;

export const PEN_WIDTH = 2;

/** Items in the form the annotate tool expects. */
export function toEngineItems(list: readonly Annot[]): Array<Record<string, unknown>> {
  return list.map((a) => {
    if (a.type === "note") return { type: "note", page: a.page, x: a.x, y: a.y, text: a.text ?? "", color: a.color };
    if (a.type === "ink") return { type: "ink", page: a.page, points: a.points, color: a.color, width: PEN_WIDTH };
    return { type: a.type, page: a.page, rects: [a.rect], color: a.color };
  });
}

export function normalize(a: [number, number], b: [number, number]): Rect {
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
}
