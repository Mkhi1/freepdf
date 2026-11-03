import { useEffect, useState } from "preact/hooks";
import { getInfo } from "../engine/client";
import { fileName, isPdf } from "../engine/files";
import type { EngineResult } from "../engine/types";
import { recordResult } from "./history";

export type FileStatus = "loading" | "ready" | "locked" | "error";

export interface FileEntry {
  path: string;
  name: string;
  status: FileStatus;
  pdf: boolean;
  pages?: number;
  bytes?: number;
  scanned?: boolean;
  password?: string;
  error?: string;
}

export interface DoneState {
  toolId: string;
  result: EngineResult;
}

interface Session {
  files: readonly FileEntry[];
  done: DoneState | null;
}

let state: Session = { files: [], done: null };
const subscribers = new Set<() => void>();

function publish(next: Session): void {
  state = next;
  subscribers.forEach((fn) => fn());
}

export function useSession(): Session {
  const [, tick] = useState(0);
  useEffect(() => {
    const fn = () => tick((n) => n + 1);
    subscribers.add(fn);
    return () => void subscribers.delete(fn);
  }, []);
  return state;
}

export function getSession(): Session {
  return state;
}

function replaceFile(path: string, patch: Partial<FileEntry>): void {
  publish({ ...state, files: state.files.map((f) => (f.path === path ? { ...f, ...patch } : f)) });
}

function newEntry(path: string): FileEntry {
  const pdf = isPdf(path);
  return { path, name: fileName(path), pdf, status: pdf ? "loading" : "ready" };
}

/** Reads page count and lock state from the viewer engine. */
export async function inspect(path: string, password?: string): Promise<void> {
  replaceFile(path, { status: "loading", error: undefined });
  try {
    const info = await getInfo(path, password);
    if (info.needs_password) {
      replaceFile(path, { status: "locked", password: undefined });
      return;
    }
    replaceFile(path, { status: "ready", pages: info.pages, bytes: info.bytes, scanned: info.scanned, password });
  } catch (error) {
    const failure = error as { code?: string; message?: string };
    const status: FileStatus = failure.code === "wrong_password" ? "locked" : "error";
    replaceFile(path, { status, error: failure.message ?? "This file could not be read." });
  }
}

export function addFiles(paths: readonly string[], limit: number | null): void {
  const known = new Set(state.files.map((f) => f.path));
  const fresh = paths.filter((p) => !known.has(p)).map(newEntry);
  const merged = [...state.files, ...fresh];
  publish({ ...state, files: limit === null ? merged : merged.slice(0, Math.max(limit, 1)) });
  fresh.filter((f) => f.pdf).forEach((f) => void inspect(f.path));
}

export function setFiles(paths: readonly string[]): void {
  publish({ ...state, files: [] });
  addFiles(paths, null);
}

export function replaceOrder(files: readonly FileEntry[]): void {
  publish({ ...state, files });
}

export function removeFile(path: string): void {
  publish({ ...state, files: state.files.filter((f) => f.path !== path) });
}

export function clearFiles(): void {
  publish({ ...state, files: [] });
}

export function setDone(done: DoneState | null): void {
  if (done) recordResult(done.toolId, done.result.outputs.map((o) => o.path));
  publish({ ...state, done });
}
