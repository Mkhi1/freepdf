import { useRef, useState } from "preact/hooks";
import { go, setDone, startCall } from "../kit";

export interface EditorRunState {
  running: boolean;
  value: number;
  message: string;
  error: string | null;
}

const IDLE: EditorRunState = { running: false, value: 0, message: "", error: null };

/** Runs the engine tool for an editor, then opens the result page. `steps` run one after another. */
export function useEditorRun(resultTool: string) {
  const [state, setState] = useState<EditorRunState>(IDLE);
  const cancelRef = useRef<(() => Promise<void>) | null>(null);

  const start = async (tool: string, args: Record<string, unknown>) => {
    if (state.running) return;
    setState({ ...IDLE, running: true, message: "Starting" });
    const call = startCall(tool, args, (p) => setState((s) => ({ ...s, value: p.value, message: p.message ?? s.message })));
    cancelRef.current = call.cancel;
    try {
      const result = await call.promise;
      setDone({ toolId: resultTool, result });
      setState(IDLE);
      go(`result/${resultTool}`);
    } catch (error) {
      const failure = error as { code?: string; message?: string };
      const message = failure.code === "cancelled" ? "Stopped. Nothing was saved." : failure.message ?? "Something went wrong. Try again.";
      setState({ ...IDLE, error: message });
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
