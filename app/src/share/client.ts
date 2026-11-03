import { useEffect, useRef, useState } from "preact/hooks";
import { inTauri, toFailure } from "../engine/client";
import { isPdf } from "../engine/files";
import { recordOpen } from "../state/history";
import type { ShareBackend, ShareHandlers } from "./backend";
import type { DoneEvent, Offer, Peer, ProgressEvent, ShareState, Transfer } from "./types";

let state: ShareState = { info: null, peers: [], transfers: new Map(), offers: [] };
const subscribers = new Set<() => void>();
let backend: Promise<ShareBackend> | null = null;

function publish(patch: Partial<ShareState>): void {
  state = { ...state, ...patch };
  subscribers.forEach((fn) => fn());
}

function putTransfer(id: string, patch: Partial<Transfer>): void {
  const before = state.transfers.get(id);
  const base: Transfer = before ?? {
    id, direction: "send", peerName: "", done: 0, total: 0, bytesPerSec: 0, file: "", status: "running", error: null, paths: [],
  };
  const next = new Map(state.transfers);
  next.set(id, { ...base, ...patch });
  publish({ transfers: next });
}

function onProgress(e: ProgressEvent): void {
  const before = state.transfers.get(e.transferId);
  if (before && before.status !== "running") return;
  const { transferId, ...rest } = e;
  putTransfer(transferId, { ...rest, peerName: e.peerName || before?.peerName || "" });
}

function onDone(e: DoneEvent): void {
  const before = state.transfers.get(e.transferId);
  putTransfer(e.transferId, {
    direction: e.direction,
    peerName: e.peerName || before?.peerName || "",
    status: e.ok ? "done" : "failed",
    error: e.error,
    paths: e.paths,
    done: e.ok ? Math.max(before?.total ?? 0, before?.done ?? 0) : before?.done ?? 0,
    bytesPerSec: e.ok ? 0 : before?.bytesPerSec ?? 0,
  });
  if (e.ok && e.direction === "receive") e.paths.filter(isPdf).forEach(recordOpen);
}

function dropOffer(offerId: string): void {
  publish({ offers: state.offers.filter((o) => o.offerId !== offerId) });
}

function onOfferClosed(offerId: string): void {
  dropOffer(offerId);
  if (state.transfers.get(offerId)?.status !== "running") return;
  putTransfer(offerId, {
    status: "failed",
    error: { code: "cancelled", message: "The other PC stopped sending. Ask them to send the files again." },
  });
}

const handlers: ShareHandlers = {
  peers: (peers) => publish({ peers }),
  offer: (offer: Offer) => publish({ offers: [...state.offers.filter((o) => o.offerId !== offer.offerId), offer] }),
  offerClosed: onOfferClosed,
  progress: onProgress,
  done: onDone,
};

async function load(): Promise<ShareBackend> {
  const api = inTauri ? (await import("./backend")).tauriBackend : (await import("./mock")).mockBackend;
  await api.subscribe(handlers);
  const [info, peers] = await Promise.all([api.info(), api.peers()]);
  publish({ info, peers });
  return api;
}

/** Starts listening once. Later calls reuse the same backend. */
function api(): Promise<ShareBackend> {
  if (!backend) {
    backend = load();
    backend.catch(() => {
      backend = null;
    });
  }
  return backend;
}

async function call<T>(run: (b: ShareBackend) => Promise<T>): Promise<T> {
  try {
    return await run(await api());
  } catch (error) {
    throw toFailure(error);
  }
}

export async function send(peerId: string, paths: string[]): Promise<string> {
  const peerName = state.peers.find((p) => p.id === peerId)?.name ?? "";
  const id = await call((b) => b.send(peerId, paths));
  if (!state.transfers.has(id)) putTransfer(id, { direction: "send", peerName, paths });
  return id;
}

export function cancel(transferId: string): Promise<boolean> {
  return call((b) => b.cancel(transferId));
}

export async function answer(offerId: string, accept: boolean, trust: boolean): Promise<boolean> {
  const offer = state.offers.find((o) => o.offerId === offerId);
  dropOffer(offerId);
  const delivered = await call((b) => b.answer(offerId, accept, trust));
  // Events may already have created the row; only fill it in when they have not.
  if (delivered && accept && offer && !state.transfers.has(offerId)) {
    putTransfer(offerId, { direction: "receive", peerName: offer.fromName, total: offer.total });
  }
  return delivered;
}

export async function addPeer(address: string): Promise<Peer> {
  const peer = await call((b) => b.addPeer(address.trim()));
  if (!state.peers.some((p) => p.id === peer.id)) publish({ peers: [...state.peers, peer] });
  return peer;
}

export async function setName(name: string): Promise<void> {
  const clean = name.trim();
  await call((b) => b.setName(clean));
  if (state.info) publish({ info: { ...state.info, name: clean } });
}

export function forgetTransfer(id: string): void {
  const next = new Map(state.transfers);
  next.delete(id);
  publish({ transfers: next });
}

/** Re-renders only when the picked part of the state changes (by identity). */
export function useShareSelect<T>(select: (s: ShareState) => T): T {
  const [, tick] = useState(0);
  const value = select(state);
  const pick = useRef(select);
  const last = useRef(value);
  pick.current = select;
  last.current = value;
  useEffect(() => {
    const fn = () => {
      if (!Object.is(pick.current(state), last.current)) tick((n) => n + 1);
    };
    subscribers.add(fn);
    // Events can land between the first render and this effect.
    fn();
    void api().catch(() => undefined);
    return () => void subscribers.delete(fn);
  }, []);
  return value;
}

const whole = (s: ShareState) => s;

export function useShare(): ShareState {
  return useShareSelect(whole);
}

export function formatSpeed(bytesPerSec: number): string {
  if (!bytesPerSec) return "";
  return `${(bytesPerSec / 1024 / 1024).toFixed(1)} MB/s`;
}
