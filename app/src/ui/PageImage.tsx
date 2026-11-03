import { useEffect, useRef, useState } from "preact/hooks";
import { engineCall } from "../engine/client";
import { imageSrc } from "../engine/files";

const MAX_AT_ONCE = 3;
let running = 0;
const waiting: Array<() => void> = [];
const cache = new Map<string, string>();

function acquire(): Promise<void> {
  if (running < MAX_AT_ONCE) {
    running += 1;
    return Promise.resolve();
  }
  return new Promise((resolve) => waiting.push(() => { running += 1; resolve(); }));
}

function release(): void {
  running -= 1;
  waiting.shift()?.();
}

export interface PageImageProps {
  file: string;
  /** 0-based page number. */
  page: number;
  width: number;
  password?: string;
  /** Only the image is drawn, with no frame. */
  bare?: boolean;
  alt?: string;
}

/** Page picture from the viewer engine. Loads when scrolled into view, a few at a time. */
export function PageImage({ file, page, width, password, bare, alt }: PageImageProps) {
  const key = `${file}|${page}|${width}`;
  const host = useRef<HTMLDivElement>(null);
  const [src, setSrc] = useState<string | undefined>(cache.get(key));
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (src || !host.current) return;
    let alive = true;
    const watcher = new IntersectionObserver((entries) => {
      if (!entries[0]?.isIntersecting) return;
      watcher.disconnect();
      void load();
    }, { rootMargin: "200px" });

    async function load() {
      await acquire();
      try {
        if (!alive) return;
        const result = await engineCall("thumb", { file, page, width, ...(password ? { password } : {}) });
        const url = imageSrc(String(result.summary.path));
        cache.set(key, url);
        if (alive) setSrc(url);
      } catch {
        if (alive) setFailed(true);
      } finally {
        release();
      }
    }

    watcher.observe(host.current);
    return () => {
      alive = false;
      watcher.disconnect();
    };
  }, [key, src, password]);

  const ratio = 1.414;
  return (
    <div ref={host} class={bare ? "pageimg bare" : "pageimg"} style={{ aspectRatio: `1 / ${ratio}` }}>
      {src ? <img src={src} alt={alt ?? `Page ${page + 1}`} draggable={false} /> : null}
      {!src && !failed ? <span class="pageimg-wait" /> : null}
      {failed ? <span class="pageimg-fail">No preview</span> : null}
    </div>
  );
}
