import type { ComponentChildren } from "preact";
import type { Box, Pt, Size } from "./geometry";

/** Anything placed on a page. Editors extend this with their own fields. */
export interface Item {
  id: string;
  page: number;
  box: Box;
  /** box: eight handles; x: left and right only; ends: two line ends; none: move only. */
  handles?: "box" | "x" | "ends" | "none";
  keepAspect?: boolean;
  minSize?: number;
  /** Height follows the content (text). */
  autoHeight?: boolean;
  /** Line ends, when handles is "ends". */
  ends?: [Pt, Pt];
}

export type DrawMode = "none" | "rect" | "line" | "ellipse" | "stroke" | "point";

export type Gesture =
  | { type: "rect"; page: number; box: Box; start: Pt; end: Pt }
  | { type: "stroke"; page: number; points: Pt[] }
  | { type: "click"; page: number; pt: Pt };

export interface PreviewStyle {
  stroke: string;
  fill?: string;
  /** Points. */
  width: number;
}

export interface RenderContext {
  scale: number;
  selected: boolean;
}

export interface DocView {
  file: string;
  password?: string;
  /** Page sizes as the viewer shows them (rotation applied), in points. */
  sizes: readonly Size[];
}

export type Render<T extends Item> = (item: T, ctx: RenderContext) => ComponentChildren;

let counter = 0;
export function newId(prefix = "i"): string {
  counter += 1;
  return `${prefix}${Date.now().toString(36)}${counter}`;
}
