import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { DoneEvent, Offer, Peer, ProgressEvent, ShareInfo } from "./types";

export interface ShareHandlers {
  peers: (peers: Peer[]) => void;
  offer: (offer: Offer) => void;
  offerClosed: (offerId: string) => void;
  progress: (event: ProgressEvent) => void;
  done: (event: DoneEvent) => void;
}

/** The Rust side in the app, or a stand-in for the browser preview. */
export interface ShareBackend {
  info(): Promise<ShareInfo>;
  peers(): Promise<Peer[]>;
  setName(name: string): Promise<void>;
  addPeer(address: string): Promise<Peer>;
  send(peerId: string, paths: string[]): Promise<string>;
  cancel(transferId: string): Promise<boolean>;
  answer(offerId: string, accept: boolean, trust: boolean): Promise<boolean>;
  subscribe(handlers: ShareHandlers): Promise<void>;
}

async function subscribe(on: ShareHandlers): Promise<void> {
  await Promise.all([
    listen<Peer[]>("share-peers", (e) => on.peers(e.payload)),
    listen<Offer>("share-offer", (e) => on.offer(e.payload)),
    listen<{ offerId: string }>("share-offer-closed", (e) => on.offerClosed(e.payload.offerId)),
    listen<ProgressEvent>("share-progress", (e) => on.progress(e.payload)),
    listen<DoneEvent>("share-done", (e) => on.done(e.payload)),
  ]);
}

export const tauriBackend: ShareBackend = {
  info: () => invoke<ShareInfo>("share_info"),
  peers: () => invoke<Peer[]>("share_peers"),
  setName: (name) => invoke<void>("share_set_name", { name }),
  addPeer: (address) => invoke<Peer>("share_add_peer", { address }),
  send: (peerId, paths) => invoke<string>("share_send", { peerId, paths }),
  cancel: (transferId) => invoke<boolean>("share_cancel", { transferId }),
  answer: (offerId, accept, trust) => invoke<boolean>("share_answer", { offerId, accept, trust }),
  subscribe,
};
