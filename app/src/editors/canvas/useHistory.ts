import { useCallback, useRef, useState } from "preact/hooks";

interface Stack<T> { past: T[]; present: T; future: T[] }

/**
 * Undo and redo over immutable values.
 * push: one undo step. checkpoint + live: a drag or typing session that is one undo step.
 */
export function useHistory<T>(initial: T) {
  const [stack, setStack] = useState<Stack<T>>({ past: [], present: initial, future: [] });
  const latest = useRef(stack);
  latest.current = stack;

  const apply = useCallback((next: Stack<T>) => {
    latest.current = next;
    setStack(next);
  }, []);

  const push = useCallback((value: T) => {
    const s = latest.current;
    apply({ past: [...s.past.slice(-99), s.present], present: value, future: [] });
  }, [apply]);

  const checkpoint = useCallback(() => {
    const s = latest.current;
    apply({ past: [...s.past.slice(-99), s.present], present: s.present, future: [] });
  }, [apply]);

  const live = useCallback((value: T) => {
    const s = latest.current;
    apply({ ...s, present: value });
  }, [apply]);

  const undo = useCallback(() => {
    const s = latest.current;
    if (!s.past.length) return;
    apply({ past: s.past.slice(0, -1), present: s.past[s.past.length - 1], future: [s.present, ...s.future] });
  }, [apply]);

  const redo = useCallback(() => {
    const s = latest.current;
    if (!s.future.length) return;
    apply({ past: [...s.past, s.present], present: s.future[0], future: s.future.slice(1) });
  }, [apply]);

  return {
    value: stack.present, push, checkpoint, live, undo, redo,
    canUndo: stack.past.length > 0, canRedo: stack.future.length > 0,
    get: () => latest.current.present,
  };
}
