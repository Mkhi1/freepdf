import { useMemo, useRef, useState } from "preact/hooks";
import { engineCall } from "../../engine/client";
import type { Rect } from "./annots";

export interface PageHits { page: number; rects: Rect[] }
export interface Hit { page: number; index: number; rect: Rect }

export interface SearchState {
  query: string;
  status: "idle" | "busy" | "done" | "error";
  message: string;
  hits: PageHits[];
  flat: Hit[];
  current: number;
}

const EMPTY: SearchState = { query: "", status: "idle", message: "", hits: [], flat: [], current: -1 };

/** Search through the viewer engine's search tool. A newer search replaces an older one still running. */
export function useSearch(file: string, password: string | undefined, currentPage: () => number) {
  const [state, setState] = useState<SearchState>(EMPTY);
  const ticket = useRef(0);

  const run = async (query: string) => {
    const text = query.trim();
    const mine = ++ticket.current;
    if (!text) { setState(EMPTY); return; }
    setState({ ...EMPTY, query: text, status: "busy" });
    try {
      const result = await engineCall("search", { file, query: text, ...(password ? { password } : {}) });
      if (mine !== ticket.current) return;
      const hits = (result.summary.hits ?? []) as PageHits[];
      const flat = hits.flatMap((h) => h.rects.map((rect, index) => ({ page: h.page, index, rect })));
      const start = Math.max(0, flat.findIndex((h) => h.page >= currentPage()));
      setState({ query: text, status: "done", message: "", hits, flat, current: flat.length ? start : -1 });
    } catch (e) {
      if (mine !== ticket.current) return;
      setState({ ...EMPTY, query: text, status: "error", message: (e as Error).message });
    }
  };

  const step = (delta: number) => setState((s) => {
    if (!s.flat.length) return s;
    return { ...s, current: (s.current + delta + s.flat.length) % s.flat.length };
  });
  const clear = () => { ticket.current += 1; setState(EMPTY); };

  const byPage = useMemo(() => new Map(state.hits.map((h) => [h.page, h.rects])), [state.hits]);
  return { state, run, step, clear, byPage };
}
