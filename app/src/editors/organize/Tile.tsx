import { memo } from "preact/compat";
import { Thumb } from "../reader/Thumb";
import { FileName } from "../../ui/FileName";
import type { PageItem, Source } from "./model";

export interface TileProps {
  item: PageItem;
  position: number;
  source?: Source;
  main: boolean;
  size: number;
  selected: boolean;
  focused: boolean;
  state: string;
  drag: Record<string, unknown>;
  password?: string;
  onSelect: (e: MouseEvent) => void;
}

const A4: [number, number] = [595, 842];

function pageBox(item: PageItem, source: Source | undefined, size: number) {
  const [w, h] = item.blank ? (source?.sizes[0] ?? A4) : (source?.sizes[item.page] ?? A4);
  const sideways = item.rotate % 180 !== 0;
  const [rw, rh] = sideways ? [h, w] : [w, h];
  const cellW = size - 20;
  const cellH = size * 1.3 - 20;
  const scale = Math.min(cellW / rw, cellH / rh);
  return { width: w * scale, height: h * scale, cellH };
}

function TileView(p: TileProps) {
  const { item, source } = p;
  const box = pageBox(item, source, p.size);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const px = Math.max(100, Math.round((box.width * dpr) / 50) * 50);
  const cls = ["otile", p.selected ? "on" : "", p.state ? `ri-${p.state}` : ""].filter(Boolean).join(" ");
  return (
    <div class={cls} role="option" aria-selected={p.selected} tabIndex={p.focused ? 0 : -1}
      data-tile={item.id} {...p.drag} onClick={p.onSelect}>
      <div class="otile-cell" style={{ height: `${box.cellH}px` }}>
        <div class="otile-page" style={{ width: `${box.width}px`, height: `${box.height}px`, transform: `rotate(${item.rotate}deg)` }}>
          {item.blank ? <span class="otile-blank">Blank</span> : (
            <Thumb file={item.source} page={item.page} width={px} password={p.password} alt={`Page ${item.page + 1}`} />
          )}
        </div>
      </div>
      <div class="otile-cap">
        <b>{p.position}</b>
        {!p.main && source && !item.blank ? <FileName name={source.name} class="otile-from" /> : null}
        {item.rotate ? <span class="otile-rot">{item.rotate}°</span> : null}
      </div>
      {p.selected ? <span class="otile-check" aria-hidden="true" /> : null}
    </div>
  );
}

export const Tile = memo(TileView);
