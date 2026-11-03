const PAGE_PREFIX = "freepdf.reader.page:";
const BOOKMARK_PREFIX = "freepdf.reader.bookmarks:";
const ZOOM_KEY = "freepdf.reader.zoom";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage can be blocked. The reader works without remembering.
  }
}

export function lastPage(path: string): number {
  const n = Number(read(PAGE_PREFIX + path));
  return Number.isInteger(n) && n >= 0 ? n : 0;
}

export function saveLastPage(path: string, page: number): void {
  write(PAGE_PREFIX + path, String(page));
}

export function loadBookmarks(path: string): readonly number[] {
  try {
    const list: unknown = JSON.parse(read(BOOKMARK_PREFIX + path) ?? "[]");
    return Array.isArray(list) ? list.filter((n) => Number.isInteger(n) && n >= 0) : [];
  } catch {
    return [];
  }
}

export function saveBookmarks(path: string, pages: readonly number[]): void {
  write(BOOKMARK_PREFIX + path, JSON.stringify(pages));
}

/** "fit" or a percentage such as 125. */
export function lastZoom(): "fit" | number {
  const raw = read(ZOOM_KEY);
  const n = Number(raw);
  return raw && raw !== "fit" && n >= 25 && n <= 500 ? n : "fit";
}

export function saveZoom(zoom: "fit" | number): void {
  write(ZOOM_KEY, String(zoom));
}
