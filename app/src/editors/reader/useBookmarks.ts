import { useState } from "preact/hooks";
import { loadBookmarks, saveBookmarks } from "./store";

/** The bookmark to jump to from this page: the next one down, wrapping round to the first. */
export function nextBookmark(pages: readonly number[], current: number): number | null {
  const others = pages.filter((page) => page !== current);
  return others.find((page) => page > current) ?? others[0] ?? null;
}

/** Bookmarks for one PDF. They live in the app, so the PDF file itself never changes. */
export function useBookmarks(path: string, pageCount: number) {
  const [list, setList] = useState(() => loadBookmarks(path).filter((page) => page < pageCount));
  const toggle = (page: number) => {
    const next = list.includes(page) ? list.filter((p) => p !== page) : [...list, page].sort((a, b) => a - b);
    setList(next);
    saveBookmarks(path, next);
  };
  return { list, toggle };
}
