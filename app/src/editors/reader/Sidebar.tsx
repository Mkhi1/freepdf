import { useEffect, useRef } from "preact/hooks";
import { Thumb } from "./Thumb";
import type { Size } from "./Shapes";

export interface SidebarProps {
  file: string;
  password?: string;
  sizes: readonly Size[];
  current: number;
  /** Pages that hold search hits, with their counts. */
  marks: ReadonlyMap<number, number>;
  bookmarks: readonly number[];
  onGo: (page: number) => void;
}

const WIDTH = 132;

export function Sidebar({ file, password, sizes, current, marks, bookmarks, onGo }: SidebarProps) {
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = list.current?.querySelector<HTMLElement>(`[data-thumb="${current}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [current]);

  return (
    <nav class="rd-thumbs" ref={list} aria-label="Pages">
      {sizes.map((size, page) => (
        <button
          key={page}
          type="button"
          data-thumb={page}
          class={page === current ? "rd-thumb on" : "rd-thumb"}
          aria-current={page === current ? "page" : undefined}
          aria-label={`Go to page ${page + 1}${bookmarks.includes(page) ? ", bookmarked" : ""}`}
          onClick={() => onGo(page)}
        >
          {bookmarks.includes(page) ? <i class="rd-ribbon small" title="Bookmarked" /> : null}
          <Thumb file={file} page={page} width={264} password={password} class="rd-thumb-img"
            style={{ width: `${WIDTH}px`, height: `${(WIDTH * size[1]) / size[0]}px` }} />
          <span class="rd-thumb-no">{page + 1}{marks.has(page) ? <i class="rd-thumb-hit" title={`${marks.get(page)} matches`} /> : null}</span>
        </button>
      ))}
    </nav>
  );
}
