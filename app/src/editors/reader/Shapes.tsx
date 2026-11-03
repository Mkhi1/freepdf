import { StickyNote } from "lucide-preact";
import type { Annot, Rect } from "./annots";
import { PEN_WIDTH } from "./annots";

export type Size = [number, number];

export function boxStyle(rect: Rect, size: Size): Record<string, string> {
  return {
    left: `${(rect[0] / size[0]) * 100}%`, top: `${(rect[1] / size[1]) * 100}%`,
    width: `${((rect[2] - rect[0]) / size[0]) * 100}%`, height: `${((rect[3] - rect[1]) / size[1]) * 100}%`,
  };
}

export function pathOf(points: ReadonlyArray<[number, number]>): string {
  return points.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
}

export interface ShapesProps {
  annots: readonly Annot[];
  size: Size;
  selected?: number | null;
  /** When set, shapes can be clicked. */
  onPick?: (annot: Annot) => void;
}

/** Annotations that are not saved yet, drawn with percentages so they fit at any zoom and in print. */
export function Shapes({ annots, size, selected, onPick }: ShapesProps) {
  const pick = (a: Annot) => (onPick ? (e: Event) => { e.stopPropagation(); onPick(a); } : undefined);
  return (
    <>
      {annots.filter((a) => a.type === "highlight" || a.type === "underline").map((a) => (
        <div
          key={a.id}
          class={`ann ann-${a.type}${selected === a.id ? " sel" : ""}${onPick ? " pick" : ""}`}
          style={{ ...boxStyle(a.rect as Rect, size), "--c": a.color }}
          onClick={pick(a)}
        />
      ))}
      <svg class="ann-ink" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="none" aria-hidden="true">
        {annots.filter((a) => a.type === "ink").map((a) => (
          <path
            key={a.id}
            d={pathOf(a.points ?? [])}
            stroke={a.color}
            stroke-width={PEN_WIDTH}
            class={`${selected === a.id ? "sel " : ""}${onPick ? "pick" : ""}`}
            onClick={pick(a)}
          />
        ))}
      </svg>
      {annots.filter((a) => a.type === "note").map((a) => (
        <button
          key={a.id}
          type="button"
          class={`ann-note${selected === a.id ? " sel" : ""}`}
          style={{ left: `${((a.x ?? 0) / size[0]) * 100}%`, top: `${((a.y ?? 0) / size[1]) * 100}%`, "--c": a.color }}
          aria-label={`Note: ${a.text ?? ""}`}
          title={a.text}
          onClick={pick(a)}
        >
          <StickyNote size={15} />
        </button>
      ))}
    </>
  );
}
