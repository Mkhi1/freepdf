import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { EngineFailure } from "./types";
import type { EngineResult, PdfInfo, Progress, ProgressHandler } from "./types";

export const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const listeners = new Map<string, ProgressHandler>();
let listening = false;
let counter = 0;

export function newCallId(): string {
  counter += 1;
  return `u${Date.now().toString(36)}-${counter}`;
}

async function ensureProgressListener(): Promise<void> {
  if (listening || !inTauri) return;
  listening = true;
  await listen<Progress>("engine-progress", (event) => {
    listeners.get(event.payload.id)?.(event.payload);
  });
}

export function toFailure(error: unknown): EngineFailure {
  if (error instanceof EngineFailure) return error;
  if (error && typeof error === "object" && "message" in error) {
    const { code, message } = error as { code?: string; message: string };
    return new EngineFailure(code ?? "tool_failed", message);
  }
  return new EngineFailure("tool_failed", typeof error === "string" ? error : "Something went wrong. Try again.");
}

export interface CallOptions {
  id?: string;
  onProgress?: ProgressHandler;
}

/** Runs one engine tool. Rejects with EngineFailure, whose message can be shown as is. */
export async function engineCall(
  tool: string,
  args: Record<string, unknown> = {},
  options: CallOptions = {},
): Promise<EngineResult> {
  const id = options.id ?? newCallId();
  if (options.onProgress) listeners.set(id, options.onProgress);
  try {
    if (!inTauri) {
      const { mockCall } = await import("./mock");
      return await mockCall(tool, args, options.onProgress);
    }
    await ensureProgressListener();
    return (await invoke<EngineResult>("engine_call", { tool, args, id })) as EngineResult;
  } catch (error) {
    throw toFailure(error);
  } finally {
    listeners.delete(id);
  }
}

export async function engineCancel(id: string): Promise<void> {
  if (!inTauri) {
    const { mockCancel } = await import("./mock");
    mockCancel();
    return;
  }
  await invoke<boolean>("engine_cancel", { id });
}

/** A call that can be cancelled while it runs. */
export function startCall(tool: string, args: Record<string, unknown>, onProgress?: ProgressHandler) {
  const id = newCallId();
  const promise = engineCall(tool, args, { id, onProgress });
  return { id, promise, cancel: () => engineCancel(id) };
}

export async function getInfo(file: string, password?: string): Promise<PdfInfo> {
  const result = await engineCall("info", { file, ...(password ? { password } : {}) });
  return result.summary as PdfInfo;
}

/** The PDF the app was opened with, for example from the right-click menu. */
export async function startupFile(): Promise<string | null> {
  if (!inTauri) return null;
  try {
    return await invoke<string | null>("startup_file");
  } catch {
    return null;
  }
}

/** Tells the shell the first frame is painted so it can show the window. */
export function announceReady(): void {
  if (!inTauri) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      void invoke("ui_ready");
    });
  });
}
