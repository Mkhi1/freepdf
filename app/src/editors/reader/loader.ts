import { engineCall } from "../../engine/client";
import { imageSrc } from "../../engine/files";

/**
 * Page picture loader for the reader. Keeps at most two requests in flight and always
 * serves the wanted page closest to what is on screen first. Requests nobody wants any more are dropped.
 */
export interface PageRequest {
  file: string;
  page: number;
  width: number;
  password?: string;
  /** Lower runs sooner. Called again each time a slot frees up. */
  priority: () => number;
  /** False once the picture is no longer needed. */
  wanted: () => boolean;
}

interface Waiting extends PageRequest { resolve: (url: string | null) => void }

const MAX_AT_ONCE = 2;
const CACHE_LIMIT = 500;
const cache = new Map<string, string>();
const waiting: Waiting[] = [];
let busy = 0;

export const cacheKey = (file: string, page: number, width: number) => `${file}|${page}|${width}`;

export function cached(file: string, page: number, width: number): string | undefined {
  return cache.get(cacheKey(file, page, width));
}

function remember(key: string, url: string): void {
  cache.set(key, url);
  if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value as string);
}

function takeNext(): Waiting | undefined {
  for (let i = waiting.length - 1; i >= 0; i -= 1) {
    if (!waiting[i].wanted()) waiting.splice(i, 1)[0].resolve(null);
  }
  if (!waiting.length) return undefined;
  let best = 0;
  for (let i = 1; i < waiting.length; i += 1) {
    if (waiting[i].priority() < waiting[best].priority()) best = i;
  }
  return waiting.splice(best, 1)[0];
}

async function pump(): Promise<void> {
  while (busy < MAX_AT_ONCE) {
    const job = takeNext();
    if (!job) return;
    busy += 1;
    void run(job);
  }
}

async function run(job: Waiting): Promise<void> {
  const key = cacheKey(job.file, job.page, job.width);
  try {
    const result = await engineCall("thumb", {
      file: job.file, page: job.page, width: job.width, ...(job.password ? { password: job.password } : {}),
    });
    const url = imageSrc(String(result.summary.path));
    remember(key, url);
    job.resolve(url);
  } catch {
    job.resolve(null);
  } finally {
    busy -= 1;
    void pump();
  }
}

/** Resolves to an image URL, or null when the request was dropped or failed. */
export function loadPage(request: PageRequest): Promise<string | null> {
  const hit = cache.get(cacheKey(request.file, request.page, request.width));
  if (hit) return Promise.resolve(hit);
  return new Promise((resolve) => {
    waiting.push({ ...request, resolve });
    void pump();
  });
}
