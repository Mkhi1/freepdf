import { useState } from "preact/hooks";
import { moveBox } from "./geometry";
import type { Box, Size } from "./geometry";
import type { Item } from "./types";
import { useEditorKeys } from "./useEditorKeys";
import { useHistory } from "./useHistory";

/** Items, selection, current page and undo for an editor, plus the keyboard shortcuts. */
export function useItemsEditor<T extends Item>(
  sizes: readonly Size[],
  move: (item: T, box: Box) => T = (item, box) => ({ ...item, box }),
) {
  const history = useHistory<T[]>([]);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const items = history.value;
  const selected = items.find((i) => i.id === selectedId) ?? null;

  const add = (item: T, select = true) => {
    history.push([...history.get(), item]);
    if (select) setSelectedId(item.id);
  };
  const remove = (id: string) => {
    history.push(history.get().filter((i) => i.id !== id));
    setSelectedId((cur) => (cur === id ? null : cur));
  };
  const patch = (id: string, change: (item: T) => T) => history.push(history.get().map((i) => (i.id === id ? change(i) : i)));
  const nudge = (dx: number, dy: number) => {
    const target = history.get().find((i) => i.id === selectedId);
    if (!target) return;
    const next = moveBox(target.box, { x: dx, y: dy }, sizes[target.page] ?? sizes[0]);
    patch(target.id, (i) => move(i, next));
  };

  useEditorKeys({
    onDelete: () => selectedId && remove(selectedId),
    onUndo: history.undo,
    onRedo: history.redo,
    onEscape: () => setSelectedId(null),
    onNudge: nudge,
  });

  const counts = sizes.map((_, p) => items.filter((i) => i.page === p).length);
  return { history, items, page, setPage, selectedId, select: setSelectedId, selected, add, remove, patch, counts };
}
