import { useEffect, useState } from "preact/hooks";
import { Download, Loader, X } from "lucide-preact";
import { inTauri } from "../engine/client";
import "./update.css";

type Update = Awaited<ReturnType<typeof import("@tauri-apps/plugin-updater").check>>;

type State =
  | { phase: "idle" }
  | { phase: "ready"; update: NonNullable<Update> }
  | { phase: "installing"; update: NonNullable<Update>; percent: number }
  | { phase: "failed"; message: string };

// Wait a little after start so the check never slows the first screen.
const CHECK_DELAY_MS = 6000;

async function findUpdate(): Promise<Update> {
  const { check } = await import("@tauri-apps/plugin-updater");
  return check();
}

/** Offers a new version when one is published on GitHub, then installs it and restarts. */
export function UpdateBanner() {
  const [state, setState] = useState<State>({ phase: "idle" });

  useEffect(() => {
    if (!inTauri) return;
    const timer = window.setTimeout(() => {
      findUpdate()
        .then((update) => update && setState({ phase: "ready", update }))
        .catch(() => undefined); // Offline or GitHub unreachable: try again next start.
    }, CHECK_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);

  const install = async (update: NonNullable<Update>) => {
    let total = 0;
    let done = 0;
    setState({ phase: "installing", update, percent: 0 });
    try {
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") total = event.data.contentLength ?? 0;
        if (event.event === "Progress") done += event.data.chunkLength;
        const percent = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
        setState({ phase: "installing", update, percent });
      });
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch {
      setState({ phase: "failed", message: "The update could not be installed. Check your internet connection and try again next time you open Free PDF." });
    }
  };

  if (state.phase === "idle") return null;
  const dismiss = () => setState({ phase: "idle" });

  return (
    <div class="update" role="status">
      {state.phase === "ready" ? (
        <>
          <Download size={16} aria-hidden="true" />
          <span class="update-text">Free PDF {state.update.version} is available.</span>
          <button type="button" class="btn primary small" onClick={() => void install(state.update)}>Update and restart</button>
          <button type="button" class="icon-btn" aria-label="Later" title="Later" onClick={dismiss}><X size={16} /></button>
        </>
      ) : null}
      {state.phase === "installing" ? (
        <>
          <Loader size={16} class="spin" aria-hidden="true" />
          <span class="update-text">Updating to {state.update.version}… {state.percent}%</span>
        </>
      ) : null}
      {state.phase === "failed" ? (
        <>
          <span class="update-text">{state.message}</span>
          <button type="button" class="icon-btn" aria-label="Close" onClick={dismiss}><X size={16} /></button>
        </>
      ) : null}
    </div>
  );
}
