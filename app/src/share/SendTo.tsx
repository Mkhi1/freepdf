import { useEffect, useRef, useState } from "preact/hooks";
import { Laptop, Send } from "lucide-preact";
import { send, useShareSelect } from "./client";
import type { Peer } from "./types";
import "./share.css";

const NO_PEERS: Peer[] = [];

function useOutsideClose(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return ref;
}

function label(status: string | undefined, pct: number): string {
  if (status === "running") return `Sending ${pct}%`;
  if (status === "done") return "Sent";
  if (status === "failed") return "Not sent";
  return "Send to device";
}

export interface SendToProps {
  path: string;
  /** Only the icon, with the status in the tooltip. */
  compact?: boolean;
  /** Draw the compact button with the .btn frame, to sit next to other .btn buttons. */
  boxed?: boolean;
}

/** A button that sends one file to a nearby device. */
export function SendTo({ path, compact, boxed }: SendToProps) {
  const [open, setOpen] = useState(false);
  const [sentId, setSentId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const ref = useOutsideClose(open, () => setOpen(false));
  // Up to hundreds of these sit in History, so each one watches only its own transfer.
  const transfer = useShareSelect((s) => (sentId ? s.transfers.get(sentId) : undefined));
  const peers = useShareSelect((s) => (open ? s.peers : NO_PEERS));
  const pct = transfer?.total ? Math.round((transfer.done / transfer.total) * 100) : 0;
  const text = error && !transfer ? "Not sent" : label(transfer?.status, pct);
  const hint = transfer?.error?.message ?? error;

  const pick = async (peerId: string) => {
    setOpen(false);
    try {
      setSentId(await send(peerId, [path]));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The file could not be sent. Try again.");
    }
  };

  return (
    <div class="sendto" ref={ref}>
      <button type="button" class={`${compact && !boxed ? "icon-btn" : "btn"}${compact && boxed ? " sendto-square" : ""} ${transfer?.status ?? ""}`} aria-haspopup="menu" aria-expanded={open}
        aria-label={compact ? text : undefined} title={hint || text} onClick={() => setOpen(!open)}>
        <Send size={16} />{compact ? null : ` ${text}`}
      </button>
      {open ? (
        <div class="sendto-pop" role="menu">
          {peers.length ? (
            peers.map((p) => (
              <button key={p.id} type="button" role="menuitem" class="sendto-item" onClick={() => void pick(p.id)}>
                <Laptop size={15} aria-hidden="true" /> <span dir="auto">{p.name}</span>
              </button>
            ))
          ) : (
            <p class="hist-meta">No devices found. Open Free PDF on the other computer, on the same network.</p>
          )}
          <a class="sendto-link" href="#/devices" onClick={() => setOpen(false)}>Nearby devices</a>
        </div>
      ) : null}
    </div>
  );
}
