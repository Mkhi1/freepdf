import { useEffect, useRef, useState } from "preact/hooks";
import "./thumb.css";
import { cached, loadPage } from "./loader";

export interface ThumbProps {
  file: string;
  page: number;
  /** Pixels wide to ask the engine for. */
  width: number;
  password?: string;
  alt?: string;
  class?: string;
  style?: Record<string, string | number>;
}

/** Page picture that loads when it comes near the screen, nearest to the viewport first. */
export function Thumb({ file, page, width, password, alt, class: className, style }: ThumbProps) {
  const host = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | undefined>(() => cached(file, page, width));
  const [near, setNear] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!host.current) return;
    const watcher = new IntersectionObserver((entries) => setNear(entries[entries.length - 1].isIntersecting), { rootMargin: "400px" });
    watcher.observe(host.current);
    return () => watcher.disconnect();
  }, []);

  useEffect(() => {
    const hit = cached(file, page, width);
    if (hit) { setSrc(hit); return; }
    if (!near) return;
    let alive = true;
    const middle = () => {
      const r = host.current?.getBoundingClientRect();
      return r ? Math.abs(r.top - window.innerHeight / 2) + 1000 : 5000;
    };
    void loadPage({ file, page, width, password, priority: middle, wanted: () => alive }).then((url) => {
      if (!alive) return;
      if (url) setSrc(url);
      else setFailed(true);
    });
    return () => { alive = false; };
  }, [file, page, width, near, password]);

  return (
    <div ref={host} class={className ? `thumb ${className}` : "thumb"} style={style}>
      {src ? <img src={src} alt={alt ?? `Page ${page + 1}`} draggable={false} /> : null}
      {!src && !failed ? <span class="pageimg-wait" /> : null}
      {failed ? <span class="pageimg-fail">No preview</span> : null}
    </div>
  );
}
