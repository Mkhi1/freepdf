import { useEffect, useRef, useState } from "preact/hooks";
import "./reorder.css";

/** Where a dragged item lands: 0 is before the first item, `count` is after the last. */
export type Slot = number;

export interface ReorderOptions {
  /** Called once when an item is dropped or moved with the keyboard. */
  onReorder: (from: number, slot: Slot) => void;
  /** Drags start only after the pointer moved this far, so plain clicks still work. */
  threshold?: number;
}

export type ItemState = "" | "dragging" | "before" | "after";

const SKIP = "button, input, textarea, select, a, [data-nodrag]";
const EDGE = 48;

/** Index an item ends up at after `slotToIndex(from, slot)` removes and re-inserts it. */
export function slotToIndex(from: number, slot: Slot): number {
  return slot > from ? slot - 1 : slot;
}

/** Moves one item to a slot without changing the original list. */
export function moveItem<T>(list: readonly T[], from: number, slot: Slot): T[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(slotToIndex(from, slot), 0, item);
  return next;
}

function scrollParent(el: HTMLElement | null): HTMLElement | null {
  for (let node = el?.parentElement ?? null; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && node.scrollHeight > node.clientHeight) return node;
  }
  return null;
}

function slotAt(items: HTMLElement[], x: number, y: number, skip: HTMLElement): Slot {
  let best = items.length;
  let bestDistance = Infinity;
  items.forEach((el, index) => {
    if (el === skip) return;
    const r = el.getBoundingClientRect();
    const dx = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
    const dy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
    const distance = dx * dx + dy * dy;
    if (distance >= bestDistance) return;
    bestDistance = distance;
    const after = dy === 0 ? x > r.left + r.width / 2 : y > r.bottom;
    best = index + (after ? 1 : 0);
  });
  return best;
}

interface Drag { from: number; el: HTMLElement; startX: number; startY: number; live: boolean; scroll: HTMLElement | null }

/**
 * Pointer based drag to reorder, for lists and grids. Uses pointer events because the
 * native window file drop blocks HTML5 drag and drop. Alt plus arrow keys move the focused item.
 */
export function useReorder({ onReorder, threshold = 6 }: ReorderOptions) {
  const [from, setFrom] = useState<number | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const drag = useRef<Drag | null>(null);
  const pointer = useRef({ x: 0, y: 0 });
  const latest = useRef(onReorder);
  latest.current = onReorder;
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  const siblings = (el: HTMLElement) =>
    Array.from(el.parentElement?.querySelectorAll<HTMLElement>(":scope > [data-ri]") ?? []);

  const finish = (commit: boolean) => {
    const d = drag.current;
    window.clearInterval(timer.current);
    drag.current = null;
    if (!d) return;
    d.el.style.transform = "";
    d.el.style.zIndex = "";
    d.el.classList.remove("ri-lift");
    if (d.live && commit) {
      const target = slotAt(siblings(d.el), pointer.current.x, pointer.current.y, d.el);
      if (target !== d.from && target !== d.from + 1) latest.current(d.from, target);
    }
    setFrom(null);
    setSlot(null);
  };

  const autoScroll = () => {
    const d = drag.current;
    if (!d?.live || !d.scroll) return;
    const r = d.scroll.getBoundingClientRect();
    const y = pointer.current.y;
    if (y < r.top + EDGE) d.scroll.scrollTop -= Math.ceil((r.top + EDGE - y) / 3);
    else if (y > r.bottom - EDGE) d.scroll.scrollTop += Math.ceil((y - (r.bottom - EDGE)) / 3);
    else return;
    const { x, y: py } = pointer.current;
    d.el.style.transform = `translate(${x - d.startX}px, ${py - d.startY}px)`;
    setSlot(slotAt(siblings(d.el), x, py, d.el));
  };

  const move = (e: PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    pointer.current = { x: e.clientX, y: e.clientY };
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (!d.live) {
      if (Math.hypot(dx, dy) < threshold) return;
      d.live = true;
      d.scroll = scrollParent(d.el);
      d.el.classList.add("ri-lift");
      d.el.style.zIndex = "30";
      setFrom(d.from);
      timer.current = window.setInterval(autoScroll, 30);
    }
    d.el.style.transform = `translate(${dx}px, ${dy}px)`;
    setSlot(slotAt(siblings(d.el), e.clientX, e.clientY, d.el));
  };

  const itemProps = (index: number) => ({
    "data-ri": index,
    "aria-roledescription": "sortable item",
    onPointerDown: (e: PointerEvent) => {
      const el = e.currentTarget as HTMLElement;
      if (e.button !== 0 || (e.target as HTMLElement).closest(SKIP)) return;
      drag.current = { from: index, el, startX: e.clientX, startY: e.clientY, live: false, scroll: null };
      pointer.current = { x: e.clientX, y: e.clientY };
      el.setPointerCapture(e.pointerId);
    },
    onPointerMove: move,
    onPointerUp: () => finish(true),
    onPointerCancel: () => finish(false),
    onKeyDown: (e: KeyboardEvent) => {
      if (!e.altKey) return;
      const back = e.key === "ArrowLeft" || e.key === "ArrowUp";
      const forward = e.key === "ArrowRight" || e.key === "ArrowDown";
      if (!back && !forward) return;
      e.preventDefault();
      latest.current(index, back ? index - 1 : index + 2);
    },
  });

  /** Visual state of an item, for a class name: a lifted item or the side with the drop line. */
  const stateOf = (index: number, count: number): ItemState => {
    if (from === null || slot === null) return "";
    if (index === from) return "dragging";
    if (slot === from || slot === from + 1) return "";
    if (index === slot) return "before";
    if (slot === count && index === count - 1) return "after";
    return "";
  };

  return { itemProps, stateOf, dragging: from !== null };
}
