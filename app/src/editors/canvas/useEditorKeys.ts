import { useEffect, useRef } from "preact/hooks";

export interface EditorKeys {
  onDelete: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onEscape: () => void;
  onNudge?: (dx: number, dy: number) => void;
}

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
}

/** Delete, undo, redo, escape and arrow nudging, except while a text box has focus. */
export function useEditorKeys(keys: EditorKeys): void {
  const latest = useRef(keys);
  latest.current = keys;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = latest.current;
      if (typing(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      const lower = e.key.toLowerCase();
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); k.onDelete(); }
      else if (mod && lower === "z") { e.preventDefault(); if (e.shiftKey) k.onRedo(); else k.onUndo(); }
      else if (mod && lower === "y") { e.preventDefault(); k.onRedo(); }
      else if (e.key === "Escape") k.onEscape();
      else if (k.onNudge && e.key.startsWith("Arrow")) {
        const step = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0;
        const dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
        e.preventDefault();
        k.onNudge(dx, dy);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
