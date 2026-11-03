import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { fitWidthScale, scaleToZoom, stepZoom, zoomToScale } from "./geometry";

const GUTTER = 48;

/** Zoom state for a scrolling page area. `fit` follows the width of the area. */
export function useZoom(pageWidthPt: number) {
  const area = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState(600);
  const [manual, setManual] = useState<number | null>(null);

  useEffect(() => {
    const node = area.current;
    if (!node) return;
    const measure = () => setAvailable(Math.max(node.clientWidth - GUTTER, 200));
    measure();
    const watcher = new ResizeObserver(measure);
    watcher.observe(node);
    return () => watcher.disconnect();
  }, []);

  const scale = manual === null ? fitWidthScale(available, pageWidthPt) : zoomToScale(manual);
  const zoom = scaleToZoom(scale);
  const zoomBy = useCallback((direction: 1 | -1) => setManual(stepZoom(scaleToZoom(scale), direction)), [scale]);
  const fit = useCallback(() => setManual(null), []);
  return { area, scale, zoom, fitted: manual === null, zoomIn: () => zoomBy(1), zoomOut: () => zoomBy(-1), fit };
}
