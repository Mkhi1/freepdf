import { useEffect, useState } from "preact/hooks";
import { FolderOpen, Laptop, Plus, Send, TriangleAlert } from "lucide-preact";
import { pickFiles, openFile } from "../engine/files";
import { HomeFrame } from "../home/HomeFrame";
import { addPeer, send, setName, useShare } from "./client";
import { Transfers } from "./Transfers";
import type { Peer, ShareInfo } from "./types";
import "./share.css";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}

function ThisDevice({ info }: { info: ShareInfo }) {
  const [draft, setDraft] = useState(info.name);
  const [error, setError] = useState("");
  useEffect(() => setDraft(info.name), [info.name]);

  const save = async () => {
    const clean = draft.trim();
    if (clean === info.name) return;
    if (!clean || clean.length > 40) {
      setError("Use a name between 1 and 40 characters.");
      return;
    }
    try {
      await setName(clean);
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  };

  return (
    <section class="share-self" aria-label="This device">
      <span class="share-dir" aria-hidden="true"><Laptop size={18} /></span>
      <div class="share-main">
        <label class="share-label" for="share-name">This computer shows up as</label>
        <input id="share-name" class="input share-name" maxLength={40} value={draft} dir="auto"
          onInput={(e) => setDraft(e.currentTarget.value)} onBlur={() => void save()}
          onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
        <span class="hist-meta">
          {info.addresses.length ? `Address ${info.addresses.join(", ")}` : "No network connection found"}
          {" · Received files go to "}{info.receiveDir}
        </span>
        {error ? <span class="share-error"><TriangleAlert size={14} /> {error}</span> : null}
      </div>
      <button type="button" class="btn small" onClick={() => void openFile(info.receiveDir)}><FolderOpen size={14} /> Open folder</button>
    </section>
  );
}

function PeerRow({ peer, onError }: { peer: Peer; onError: (text: string) => void }) {
  const pick = async () => {
    const paths = await pickFiles({ accepts: [], multiple: true, title: `Send files to ${peer.name}` });
    if (!paths.length) return;
    try {
      await send(peer.id, paths);
      onError("");
    } catch (e) {
      onError(errorText(e));
    }
  };
  return (
    <li class="hist-row share-row">
      <span class="share-dir" aria-hidden="true"><Laptop size={16} /></span>
      <div class="share-main">
        <span class="hist-name" dir="auto">{peer.name}</span>
        <span class="hist-meta">{peer.address}{peer.manual ? " · Added by address" : ""}</span>
      </div>
      <div class="hist-actions">
        <button type="button" class="btn small primary" onClick={() => void pick()}><Send size={14} /> Send files</button>
      </div>
    </li>
  );
}

function AddByAddress() {
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: Event) => {
    e.preventDefault();
    if (!address.trim() || busy) return;
    setBusy(true);
    try {
      await addPeer(address);
      setAddress("");
      setError("");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form class="share-add" onSubmit={(e) => void submit(e)}>
      <label class="share-label" for="share-ip">Not listed? Add it by IP address</label>
      <div class="share-add-row">
        <input id="share-ip" class="input" placeholder="192.168.1.31" inputMode="decimal" dir="ltr"
          value={address} onInput={(e) => setAddress(e.currentTarget.value)} />
        <button type="submit" class="btn" disabled={busy || !address.trim()}><Plus size={15} /> {busy ? "Connecting" : "Add device"}</button>
      </div>
      {error ? <span class="share-error"><TriangleAlert size={14} /> {error}</span> : null}
    </form>
  );
}

/** Send files straight to another computer running Free PDF on the same network. */
export function Devices() {
  const { info, peers, transfers } = useShare();
  const [sendError, setSendError] = useState("");

  return (
    <HomeFrame active="devices">
      <div class="hist-head">
        <div>
          <h1>Nearby devices</h1>
          <p>Send files straight to another computer on your network. Nothing goes through the internet.</p>
        </div>
      </div>
      {info ? <ThisDevice info={info} /> : null}
      <h2 class="hist-day">On this network</h2>
      {peers.length ? (
        <ul class="hist-list">{peers.map((p) => <PeerRow key={p.id} peer={p} onError={setSendError} />)}</ul>
      ) : (
        <p class="share-empty">
          Looking for other computers. Open Free PDF on the other computer and make sure both are on the same
          Wi-Fi or network. If Windows asks whether Free PDF may use the network, choose Allow.
        </p>
      )}
      {sendError ? <p class="error share-gap" role="alert"><TriangleAlert size={16} /> <span>{sendError}</span></p> : null}
      <AddByAddress />
      <Transfers transfers={transfers} />
    </HomeFrame>
  );
}
