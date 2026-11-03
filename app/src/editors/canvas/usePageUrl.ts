import { useEffect, useState } from "preact/hooks";
import { engineCall } from "../../engine/client";
import { imageSrc } from "../../engine/files";

const cache = new Map<string, string>();

/** Picture of one page from the viewer engine. Keeps the previous picture on screen while a sharper one loads. */
export function usePageUrl(file: string, page: number, width: number, password?: string, delay = 120) {
  const key = `${file}|${page}|${width}`;
  const [shown, setShown] = useState<{ key: string; url: string } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const hit = cache.get(key);
    if (hit) {
      setShown({ key, url: hit });
      setFailed(false);
      return;
    }
    let alive = true;
    const timer = setTimeout(() => {
      engineCall("thumb", { file, page, width, ...(password ? { password } : {}) })
        .then((r) => {
          const url = imageSrc(String(r.summary.path));
          cache.set(key, url);
          if (alive) { setShown({ key, url }); setFailed(false); }
        })
        .catch(() => alive && setFailed(true));
    }, delay);
    return () => { alive = false; clearTimeout(timer); };
  }, [key, password]);

  return { url: shown?.url ?? null, failed };
}
