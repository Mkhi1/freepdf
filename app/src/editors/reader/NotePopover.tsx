import { useEffect, useRef, useState } from "preact/hooks";
import { Check, Trash2 } from "lucide-preact";
import type { Annot } from "./annots";
import type { Size } from "./Shapes";

export interface NotePopoverProps {
  note: Annot;
  size: Size;
  /** Text to keep, or null to delete the note. */
  onText: (id: number, text: string | null) => void;
}

export function NotePopover({ note, size, onText }: NotePopoverProps) {
  const [text, setText] = useState(note.text ?? "");
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    box.current?.focus();
    const timer = window.setTimeout(() => { if (document.activeElement !== box.current) box.current?.focus(); }, 60);
    return () => window.clearTimeout(timer);
  }, []);
  const done = () => onText(note.id, text.trim() ? text.trim() : null);
  const onRight = (note.x ?? 0) > size[0] * 0.6;
  return (
    <div
      class={onRight ? "rd-notepop left" : "rd-notepop"}
      style={{ left: `${((note.x ?? 0) / size[0]) * 100}%`, top: `${((note.y ?? 0) / size[1]) * 100}%` }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <textarea
        ref={box}
        dir="auto"
        rows={4}
        placeholder="Write a note"
        value={text}
        onInput={(e) => setText(e.currentTarget.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.stopPropagation(); done(); }
          else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); done(); }
        }}
      />
      <div class="rd-notepop-row">
        <button type="button" class="btn small" onClick={() => onText(note.id, null)}><Trash2 size={14} /> Delete</button>
        <button type="button" class="btn small primary" onClick={done}><Check size={14} /> Done</button>
      </div>
    </div>
  );
}
