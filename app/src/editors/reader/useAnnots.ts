import { useState } from "preact/hooks";
import { newAnnotId } from "./annots";
import type { Annot } from "./annots";

/** Marks that are not saved into the file yet. Every change builds a new list. */
export function useAnnots() {
  const [list, setList] = useState<readonly Annot[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);

  return {
    list,
    selected,
    editing,
    add: (draft: Omit<Annot, "id">) => {
      const id = newAnnotId();
      setList((l) => [...l, { ...draft, id }]);
      if (draft.type === "note") setEditing(id);
      else setSelected(null);
    },
    pick: (annot: Annot) => {
      if (annot.type === "note") { setEditing(annot.id); setSelected(null); }
      else setSelected(annot.id);
    },
    setNoteText: (id: number, text: string | null) => {
      setEditing(null);
      setList((l) => (text === null ? l.filter((a) => a.id !== id) : l.map((a) => (a.id === id ? { ...a, text } : a))));
    },
    removeSelected: () => {
      if (selected === null) return false;
      setList((l) => l.filter((a) => a.id !== selected));
      setSelected(null);
      return true;
    },
    undo: () => {
      setEditing(null);
      setList((l) => l.slice(0, -1));
    },
    clear: () => { setList([]); setSelected(null); setEditing(null); },
    deselect: () => { setSelected(null); setEditing(null); },
  };
}
