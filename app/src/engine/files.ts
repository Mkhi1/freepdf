import { convertFileSrc } from "@tauri-apps/api/core";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openPath, revealItemInDir } from "@tauri-apps/plugin-opener";
import { inTauri } from "./client";

export function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function fileExt(path: string): string {
  const name = fileName(path);
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

export function isPdf(path: string): boolean {
  return fileExt(path) === "pdf";
}

export function formatBytes(bytes?: number): string {
  if (bytes === undefined || Number.isNaN(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** URL for an image the engine wrote into the temp or local app data folder. */
export function imageSrc(path: string): string {
  if (path.startsWith("data:") || !inTauri) return path;
  return convertFileSrc(path);
}

export function matchesAccepted(path: string, accepts: readonly string[]): boolean {
  return accepts.length === 0 || accepts.includes(fileExt(path));
}

export interface PickOptions {
  accepts: readonly string[];
  multiple: boolean;
  title?: string;
}

/** Native file picker. Resolves to real file paths, or an empty list when cancelled. */
export async function pickFiles(options: PickOptions): Promise<string[]> {
  if (!inTauri) {
    const { mockPick } = await import("./mock");
    return mockPick(options.accepts, options.multiple);
  }
  const chosen = await openDialog({
    multiple: options.multiple,
    title: options.title,
    filters: options.accepts.length ? [{ name: "Files", extensions: [...options.accepts] }] : undefined,
  });
  if (!chosen) return [];
  return Array.isArray(chosen) ? chosen : [chosen];
}

export type DropHandler = (paths: string[]) => void;
export type HoverHandler = (hovering: boolean) => void;

/** Whole-window drag and drop with real paths. Returns an unsubscribe function. */
export function watchDrops(onDrop: DropHandler, onHover: HoverHandler): () => void {
  if (!inTauri) return () => undefined;
  let stop: (() => void) | undefined;
  let cancelled = false;
  void getCurrentWebview()
    .onDragDropEvent((event) => {
      const payload = event.payload;
      if (payload.type === "enter" || payload.type === "over") onHover(true);
      else if (payload.type === "leave") onHover(false);
      else if (payload.type === "drop") {
        onHover(false);
        onDrop(payload.paths);
      }
    })
    .then((unlisten) => {
      if (cancelled) unlisten();
      else stop = unlisten;
    });
  return () => {
    cancelled = true;
    stop?.();
  };
}

export async function openFile(path: string): Promise<void> {
  if (inTauri) await openPath(path);
}

export async function showInFolder(path: string): Promise<void> {
  if (inTauri) await revealItemInDir(path);
}
