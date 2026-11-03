import type { FileEntry } from "../state/session";

/** The first file as engine args, with its password when one was entered. */
export function fileArgs(files: readonly FileEntry[]): Record<string, unknown> {
  const first = files[0];
  if (!first) return {};
  return { file: first.path, ...(first.password ? { password: first.password } : {}) };
}

/** Turns "1-3, 7" into 0-based page numbers. Returns undefined for blank text, null for bad text. */
export function parsePageList(text: string): number[] | undefined | null {
  const cleaned = text.trim();
  if (!cleaned) return undefined;
  const pages = new Set<number>();
  for (const part of cleaned.split(/[,\s]+/).filter(Boolean)) {
    const match = /^(\d+)(?:-(\d+))?$/.exec(part);
    if (!match) return null;
    const from = Number(match[1]);
    const to = match[2] ? Number(match[2]) : from;
    if (from < 1 || to < from || to - from > 5000) return null;
    for (let n = from; n <= to; n += 1) pages.add(n - 1);
  }
  return [...pages].sort((a, b) => a - b);
}

export const BAD_PAGES = "Write pages like 1-3, 7. Numbers start at 1.";

export function pageListProblem(text: string): string | null {
  return parsePageList(text) === null ? BAD_PAGES : null;
}

export function paths(files: readonly FileEntry[]): string[] {
  return files.map((f) => f.path);
}
