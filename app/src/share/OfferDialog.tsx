import { useEffect, useRef, useState } from "preact/hooks";
import { Download } from "lucide-preact";
import { formatBytes } from "../engine/files";
import { FileName } from "../ui/FileName";
import { answer, useShare } from "./client";
import type { Offer } from "./types";
import "./share.css";

const SHOWN_FILES = 8;

function Dialog({ offer }: { offer: Offer }) {
  const [trust, setTrust] = useState(false);
  const acceptRef = useRef<HTMLButtonElement>(null);
  const reply = (accept: boolean) => void answer(offer.offerId, accept, accept && trust).catch(() => undefined);

  useEffect(() => {
    acceptRef.current?.focus();
    setTrust(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") reply(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [offer.offerId]);

  const count = offer.files.length;
  const extra = count - SHOWN_FILES;
  return (
    <div class="share-backdrop">
      <div class="share-dialog" role="dialog" aria-modal="true" aria-labelledby="share-offer-title">
        <span class="share-dir big" aria-hidden="true"><Download size={20} /></span>
        <h2 id="share-offer-title" dir="auto">{offer.fromName} wants to send you {count === 1 ? "a file" : `${count} files`}</h2>
        <ul class="share-files">
          {offer.files.slice(0, SHOWN_FILES).map((f, i) => (
            <li key={`${i}-${f.name}`}><FileName name={f.name} /><span>{formatBytes(f.size)}</span></li>
          ))}
          {extra > 0 ? <li class="share-more">and {extra} more</li> : null}
        </ul>
        <p class="hist-meta">{formatBytes(offer.total)} in total. Files are saved to Downloads\Free PDF.</p>
        <label class="share-trust">
          <input type="checkbox" checked={trust} onChange={(e) => setTrust(e.currentTarget.checked)} />
          Always accept from this device
        </label>
        <div class="share-dialog-actions">
          <button type="button" class="btn" onClick={() => reply(false)}>Decline</button>
          <button type="button" class="btn primary" ref={acceptRef} onClick={() => reply(true)}>Accept</button>
        </div>
      </div>
    </div>
  );
}

/** Asks before saving files another device sends. Mounted once, outside the routes. */
export function OfferDialog() {
  const { offers } = useShare();
  const first = offers[0];
  return first ? <Dialog key={first.offerId} offer={first} /> : null;
}
