import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import type { RefObject } from "preact";

export interface Layout {
  /** Top of each row in px. */
  tops: number[];
  total: number;
}

export function layoutRows(heights: readonly number[], gap: number, pad: number): Layout {
  const tops: number[] = [];
  let y = pad;
  for (const h of heights) {
    tops.push(y);
    y += h + gap;
  }
  return { tops, total: y - gap + pad };
}

/** Index of the last row that starts at or above y. */
export function rowAt(tops: readonly number[], y: number): number {
  let lo = 0;
  let hi = tops.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (tops[mid] <= y) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

export interface Visible {
  first: number;
  last: number;
  /** Row that holds the upper third of the viewport. */
  current: number;
  viewport: number;
}

/** Tracks which rows are on screen (plus a margin of one viewport) as the container scrolls. */
export function useVisibleRows(box: RefObject<HTMLElement>, layout: Layout, heights: readonly number[]): Visible {
  const [top, setTop] = useState(0);
  const [viewport, setViewport] = useState(800);
  const frame = useRef(0);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const read = () => {
      frame.current = 0;
      setTop(el.scrollTop);
      setViewport(el.clientHeight);
    };
    const onScroll = () => { if (!frame.current) frame.current = requestAnimationFrame(read); };
    read();
    el.addEventListener("scroll", onScroll, { passive: true });
    const resize = new ResizeObserver(onScroll);
    resize.observe(el);
    return () => {
      el.removeEventListener("scroll", onScroll);
      resize.disconnect();
      cancelAnimationFrame(frame.current);
    };
  }, [box.current]);

  return useMemo(() => {
    const count = heights.length;
    if (!count) return { first: 0, last: -1, current: 0, viewport };
    const first = Math.max(0, rowAt(layout.tops, top - viewport) );
    const last = Math.min(count - 1, rowAt(layout.tops, top + viewport * 2));
    const current = rowAt(layout.tops, top + viewport * 0.3);
    return { first, last, current, viewport };
  }, [top, viewport, layout, heights.length]);
}

/** Keeps the same spot in the document when the row heights change, for example while zooming. */
export function useKeepPosition(box: RefObject<HTMLElement>, layout: Layout, key: unknown): void {
  const anchor = useRef({ row: 0, fraction: 0 });
  const prev = useRef({ layout, key });
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    if (prev.current.key !== key && prev.current.layout !== layout) {
      const { row, fraction } = anchor.current;
      const height = (layout.tops[row + 1] ?? layout.total) - layout.tops[row];
      el.scrollTop = layout.tops[row] + fraction * height;
    }
    prev.current = { layout, key };
  }, [layout, key]);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const note = () => {
      const row = rowAt(prev.current.layout.tops, el.scrollTop);
      const tops = prev.current.layout.tops;
      const height = (tops[row + 1] ?? prev.current.layout.total) - tops[row];
      anchor.current = { row, fraction: Math.max(0, (el.scrollTop - tops[row]) / Math.max(height, 1)) };
    };
    note();
    el.addEventListener("scroll", note, { passive: true });
    return () => el.removeEventListener("scroll", note);
  }, [box.current]);
}
