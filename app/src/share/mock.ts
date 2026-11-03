import { fileName } from "../engine/files";
import type { ShareBackend, ShareHandlers } from "./backend";
import type { Offer, Peer, ShareInfo } from "./types";

const MB = 1024 * 1024;

const info: ShareInfo = {
  id: "a1b2c3d4e5f60718",
  name: "Study laptop",
  port: 47821,
  addresses: ["192.168.1.24"],
  receiveDir: "C:\\Users\\Student\\Downloads\\Free PDF",
};

let peers: Peer[] = [
  { id: "9f8e7d6c5b4a3921", name: "Living room PC", address: "192.168.1.31:47821", manual: false },
  { id: "1122334455667788", name: "Library desktop", address: "192.168.1.57:47821", manual: true },
];

const sampleOffer: Offer = {
  offerId: "mock-offer",
  fromId: "9f8e7d6c5b4a3921",
  fromName: "Living room PC",
  files: [
    { name: "Chemistry past papers.pdf", size: 18.4 * MB },
    { name: "Revision timetable.docx", size: 220 * 1024 },
  ],
  total: 18.4 * MB + 220 * 1024,
};

let handlers: ShareHandlers | null = null;
let counter = 0;
const timers = new Map<string, number>();

function simulate(id: string, peerName: string, paths: string[], direction: "send" | "receive"): void {
  const total = 46 * MB;
  let done = 0;
  const timer = window.setInterval(() => {
    done = Math.min(total, done + 4.6 * MB);
    const file = fileName(paths[Math.min(paths.length - 1, Math.floor((done / total) * paths.length))] ?? "");
    handlers?.progress({ transferId: id, direction, peerName, done, total, bytesPerSec: 92 * MB, file });
    if (done < total) return;
    window.clearInterval(timer);
    timers.delete(id);
    handlers?.done({ transferId: id, direction, peerName, ok: true, paths, error: null });
  }, 120);
  timers.set(id, timer);
}

function seed(on: ShareHandlers): void {
  const paths = ["C:\\Users\\Student\\Downloads\\Free PDF\\Biology notes - chapter 4.pdf"];
  on.progress({ transferId: "mock-done", direction: "receive", peerName: "Living room PC", done: 4.2 * MB, total: 4.2 * MB, bytesPerSec: 0, file: "" });
  on.done({ transferId: "mock-done", direction: "receive", peerName: "Living room PC", ok: true, paths, error: null });
  if (location.search.includes("offer")) on.offer(sampleOffer);
}

export const mockBackend: ShareBackend = {
  info: async () => info,
  peers: async () => peers,
  setName: async (name) => {
    info.name = name;
  },
  addPeer: async (address) => {
    const peer = { id: `m${Date.now()}`, name: `Device at ${address}`, address, manual: true };
    peers = [...peers, peer];
    handlers?.peers(peers);
    return peer;
  },
  send: async (peerId, paths) => {
    counter += 1;
    const id = `mock-send-${counter}`;
    simulate(id, peers.find((p) => p.id === peerId)?.name ?? "Device", paths, "send");
    return id;
  },
  cancel: async (transferId) => {
    const timer = timers.get(transferId);
    if (timer === undefined) return false;
    window.clearInterval(timer);
    timers.delete(transferId);
    const error = { code: "cancelled", message: "The transfer was cancelled." };
    handlers?.done({ transferId, direction: "send", peerName: "", ok: false, paths: [], error });
    return true;
  },
  answer: async (offerId, accept) => {
    if (accept && offerId === sampleOffer.offerId) {
      const paths = sampleOffer.files.map((f) => `${info.receiveDir}\\${f.name}`);
      simulate(offerId, sampleOffer.fromName, paths, "receive");
    }
    return true;
  },
  subscribe: async (on) => {
    handlers = on;
    seed(on);
  },
};
