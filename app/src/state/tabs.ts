import { useEffect, useState } from "preact/hooks";
import { fileName } from "../engine/files";
import { go } from "./router";
import { setFiles } from "./session";

export interface DocTab {
  path: string;
  name: string;
}

const subscribers = new Set<() => void>();
let tabs: readonly DocTab[] = [];
let guard: (() => boolean) | null = null;

function publish(next: readonly DocTab[]): void {
  tabs = next;
  subscribers.forEach((fn) => fn());
}

export function useTabs(): readonly DocTab[] {
  const [, tick] = useState(0);
  useEffect(() => {
    const fn = () => tick((n) => n + 1);
    subscribers.add(fn);
    return () => void subscribers.delete(fn);
  }, []);
  return tabs;
}

/** The reader sets this while it holds unsaved marks, so anything that leaves it can ask first. */
export function setLeaveGuard(check: (() => boolean) | null): void {
  guard = check;
}

export function mayLeave(): boolean {
  return guard ? guard() : true;
}

export function ensureTab(path: string): void {
  if (!tabs.some((t) => t.path === path)) publish([...tabs, { path, name: fileName(path) }]);
}

export function replaceTab(oldPath: string, newPath: string): void {
  publish(tabs.map((t) => (t.path === oldPath ? { path: newPath, name: fileName(newPath) } : t)));
}

export function showDocument(path: string): void {
  setFiles([path]);
  go("editor/reader");
}

export function openDocuments(paths: readonly string[]): void {
  if (!paths.length) return;
  paths.forEach(ensureTab);
  showDocument(paths[0]);
}

/** Closes a tab and shows the one beside it, or the home page when it was the last. */
export function closeTab(path: string, active: boolean): void {
  const index = tabs.findIndex((t) => t.path === path);
  const remaining = tabs.filter((t) => t.path !== path);
  publish(remaining);
  if (!active) return;
  const next = remaining[Math.min(index, remaining.length - 1)];
  if (next) showDocument(next.path);
  else go("");
}
