import { useRef, useState } from "preact/hooks";
import { startCall } from "../engine/client";
import { go } from "../state/router";
import { setDone } from "../state/session";
import type { FileEntry } from "../state/session";
import type { FormSpec, Opts } from "../options/types";
import type { ToolDef } from "../tools/registry";

export interface RunState {
  phase: "idle" | "running";
  value: number;
  message: string;
  error: string | null;
  note: string | null;
}

const IDLE: RunState = { phase: "idle", value: 0, message: "", error: null, note: null };

export function useRun(tool: ToolDef, spec: FormSpec | null, opts: Opts, files: readonly FileEntry[]) {
  const [state, setState] = useState<RunState>(IDLE);
  const cancelRef = useRef<(() => Promise<void>) | null>(null);

  const start = async () => {
    if (!spec || state.phase === "running") return;
    setState({ ...IDLE, phase: "running", message: "Starting" });
    const call = startCall(tool.id, spec.toArgs(opts, files), (p) =>
      setState((s) => ({ ...s, value: p.value, message: p.message ?? s.message })),
    );
    cancelRef.current = call.cancel;
    try {
      const result = await call.promise;
      setDone({ toolId: tool.id, result });
      setState(IDLE);
      go(`result/${tool.id}`);
    } catch (error) {
      const failure = error as { code?: string; message?: string };
      if (failure.code === "cancelled") {
        setState({ ...IDLE, note: "Stopped. Nothing was saved." });
      } else {
        setState({ ...IDLE, error: failure.message ?? "Something went wrong. Try again." });
      }
    } finally {
      cancelRef.current = null;
    }
  };

  const cancel = () => {
    void cancelRef.current?.();
    setState((s) => ({ ...s, message: "Stopping" }));
  };

  return { state, start, cancel };
}
