import { useState } from "preact/hooks";

interface Timeline<T> { present: T; past: T[]; future: T[] }

/** Value with undo and redo. Every change keeps the old value, nothing is mutated. */
export function useHistory<T>(initial: T) {
  const [line, setLine] = useState<Timeline<T>>({ present: initial, past: [], future: [] });
  return {
    value: line.present,
    canUndo: line.past.length > 0,
    canRedo: line.future.length > 0,
    set: (next: T) => setLine((l) => ({ present: next, past: [...l.past.slice(-99), l.present], future: [] })),
    undo: () => setLine((l) => (l.past.length
      ? { present: l.past[l.past.length - 1], past: l.past.slice(0, -1), future: [l.present, ...l.future] } : l)),
    redo: () => setLine((l) => (l.future.length
      ? { present: l.future[0], past: [...l.past, l.present], future: l.future.slice(1) } : l)),
    reset: (value: T) => setLine({ present: value, past: [], future: [] }),
  };
}
