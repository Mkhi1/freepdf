import { useEffect, useRef, useState } from "preact/hooks";
import type { DocView } from "./types";
import { usePageUrl } from "./usePageUrl";

function ThumbImage({ doc, page }: { doc: DocView; page: number }) {
  const { url } = usePageUrl(doc.file, page, 160, doc.password, 0);
  return url ? <img src={url} alt="" draggable={false} /> : null;
}

function Thumb(props: { doc: DocView; page: number; on: boolean; count: number; onPick: () => void }) {
  const host = useRef<HTMLButtonElement>(null);
  const [seen, setSeen] = useState(false);
  const size = props.doc.sizes[props.page];

  useEffect(() => {
    if (!host.current || seen) return;
    const watcher = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) { setSeen(true); watcher.disconnect(); }
    }, { rootMargin: "300px" });
    watcher.observe(host.current);
    return () => watcher.disconnect();
  }, [seen]);

  useEffect(() => {
    if (props.on) host.current?.scrollIntoView({ block: "nearest" });
  }, [props.on]);

  return (
    <button
      ref={host}
      type="button"
      class={props.on ? "ed-thumb on" : "ed-thumb"}
      aria-label={`Page ${props.page + 1}`}
      aria-current={props.on ? "page" : undefined}
      onClick={props.onPick}
    >
      <span class="ed-thumb-img" style={{ aspectRatio: `${size?.w ?? 1} / ${size?.h ?? 1.414}` }}>
        {seen ? <ThumbImage doc={props.doc} page={props.page} /> : null}
        {props.count > 0 ? <span class="ed-thumb-count">{props.count}</span> : null}
      </span>
      <span>{props.page + 1}</span>
    </button>
  );
}

/** Column of page thumbnails. The badge shows how many items sit on a page. */
export function PageStrip(props: { doc: DocView; page: number; counts: readonly number[]; onPage: (page: number) => void }) {
  return (
    <nav class="ed-strip" aria-label="Pages">
      {props.doc.sizes.map((_, i) => (
        <Thumb key={i} doc={props.doc} page={i} on={i === props.page} count={props.counts[i] ?? 0} onPick={() => props.onPage(i)} />
      ))}
    </nav>
  );
}
