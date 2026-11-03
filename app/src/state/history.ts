import { useEffect, useState } from "preact/hooks";
import { fileName } from "../engine/files";

export interface HistoryEntry {
  path: string;
  name: string;
  at: number;
  /** The tool that made this file, or null when it was only opened. */
  toolId: string | null;
}

const KEY = "freepdf.history";
const MAX_ENTRIES = 200;
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const TOOLS_KEY = "freepdf.recent-tools";
const TOOL_TILES = 14;
const COMMON_TOOLS = [
  "edit", "sign", "merge", "split", "compress", "pdf_to_word", "organize", "page_numbers", "ocr", "pdf_to_images",
  "watermark", "crop", "pdf_to_ppt", "compare",
];

const subscribers = new Set<() => void>();
let entries: readonly HistoryEntry[] = load();
let recentTools: readonly string[] = loadTools();

function valid(item: Partial<HistoryEntry>): item is HistoryEntry {
  return typeof item?.path === "string" && typeof item.name === "string" && typeof item.at === "number";
}

function load(): readonly HistoryEntry[] {
  try {
    const list: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(list) ? list.filter(valid) : [];
  } catch {
    return [];
  }
}

function loadTools(): readonly string[] {
  try {
    const list: unknown = JSON.parse(localStorage.getItem(TOOLS_KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function publish(next: readonly HistoryEntry[]): void {
  entries = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage can be blocked. History then lasts until the app closes.
  }
  subscribers.forEach((fn) => fn());
}

function samePath(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

function remember(paths: readonly string[], toolId: string | null): void {
  const at = Date.now();
  const fresh = paths.map((path) => ({ path, name: fileName(path), at, toolId }));
  const older = entries.filter((e) => !paths.some((p) => samePath(p, e.path)));
  publish([...fresh, ...older].slice(0, MAX_ENTRIES));
}

export function recordOpen(path: string): void {
  remember([path], null);
}

export function recordResult(toolId: string, paths: readonly string[]): void {
  if (paths.length) remember(paths, toolId);
  recentTools = [toolId, ...recentTools.filter((id) => id !== toolId)].slice(0, TOOL_TILES);
  try {
    localStorage.setItem(TOOLS_KEY, JSON.stringify(recentTools));
  } catch {
    // Storage can be blocked. Recent tools then last until the app closes.
  }
  subscribers.forEach((fn) => fn());
}

/** The tools used last, then the common ones, so the home page always has a full row. */
export function useRecentTools(): readonly string[] {
  useHistory();
  return [...recentTools, ...COMMON_TOOLS.filter((id) => !recentTools.includes(id))].slice(0, TOOL_TILES);
}

export function removeEntry(path: string): void {
  publish(entries.filter((e) => !samePath(e.path, path)));
}

export function clearHistory(): void {
  publish([]);
}

export function useHistory(): readonly HistoryEntry[] {
  const [, tick] = useState(0);
  useEffect(() => {
    const fn = () => tick((n) => n + 1);
    subscribers.add(fn);
    return () => void subscribers.delete(fn);
  }, []);
  return entries;
}

function plural(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
}

export function timeAgo(at: number, now: number = Date.now()): string {
  const gap = now - at;
  if (gap < MINUTE) return "Just now";
  if (gap < HOUR) return plural(Math.floor(gap / MINUTE), "minute");
  if (gap < DAY) return plural(Math.floor(gap / HOUR), "hour");
  if (gap < 2 * DAY) return "Yesterday";
  if (gap < 7 * DAY) return plural(Math.floor(gap / DAY), "day");
  return new Date(at).toLocaleDateString();
}

export function dayGroup(at: number, now: number = Date.now()): string {
  const startOfToday = new Date(now).setHours(0, 0, 0, 0);
  if (at >= startOfToday) return "Today";
  if (at >= startOfToday - DAY) return "Yesterday";
  if (at >= startOfToday - 6 * DAY) return "This week";
  return "Earlier";
}
