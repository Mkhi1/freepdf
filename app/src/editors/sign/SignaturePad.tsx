import { useRef, useState } from "preact/hooks";
import { Eraser } from "lucide-preact";
import type { Pt } from "../canvas/geometry";
import { pathOf } from "../canvas/ItemViews";
import { PAD_H, PAD_W, PEN_WIDTH } from "./assets";

const INKS = ["#111111", "#0d1a73", "#0b6b3a", "#b3261e"];

/** Mouse drawing area. Only the strokes are kept, so the signature has no background. */
export function SignaturePad(props: { color: string; onColor: (c: string) => void; strokes: Pt[][]; onStrokes: (s: Pt[][]) => void }) {
  const area = useRef<SVGSVGElement>(null);
  const [live, setLive] = useState<Pt[] | null>(null);
  const current = useRef<Pt[] | null>(null);

  const at = (e: PointerEvent): Pt => {
    const r = area.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * PAD_W, y: ((e.clientY - r.top) / r.height) * PAD_H };
  };
  const down = (e: PointerEvent) => {
    area.current!.setPointerCapture(e.pointerId);
    current.current = [at(e)];
    setLive(current.current);
  };
  const move = (e: PointerEvent) => {
    if (!current.current) return;
    current.current = [...current.current, at(e)];
    setLive(current.current);
  };
  const up = () => {
    const stroke = current.current;
    current.current = null;
    setLive(null);
    if (stroke && stroke.length > 1) props.onStrokes([...props.strokes, stroke]);
  };

  return (
    <div class="group">
      <svg
        ref={area}
        class="ed-pad ed-checker"
        viewBox={`0 0 ${PAD_W} ${PAD_H}`}
        role="img"
        aria-label="Signature drawing area"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
      >
        <line x1="16" y1={PAD_H - 34} x2={PAD_W - 16} y2={PAD_H - 34} stroke="#9aa9b5" stroke-dasharray="4 5" />
        {[...props.strokes, ...(live ? [live] : [])].map((s) => (
          <path d={pathOf(s)} fill="none" stroke={props.color} stroke-width={PEN_WIDTH} stroke-linecap="round" stroke-linejoin="round" />
        ))}
      </svg>
      <div class="btn-row" style={{ alignItems: "center" }}>
        <div class="ed-swatches">
          {INKS.map((c) => (
            <button type="button" aria-label={`Ink ${c}`} class={c === props.color ? "ed-swatch on" : "ed-swatch"} style={{ background: c }} onClick={() => props.onColor(c)} />
          ))}
        </div>
        <span class="ed-grow" />
        <button type="button" class="btn small" disabled={!props.strokes.length} onClick={() => props.onStrokes([])}><Eraser size={14} /> Clear</button>
      </div>
    </div>
  );
}
