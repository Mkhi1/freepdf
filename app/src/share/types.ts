export interface ShareInfo {
  id: string;
  name: string;
  port: number;
  addresses: string[];
  receiveDir: string;
}

export interface Peer {
  id: string;
  name: string;
  /** "ip:port" */
  address: string;
  manual: boolean;
}

export interface OfferFile {
  name: string;
  size: number;
}

export interface Offer {
  offerId: string;
  fromId: string;
  fromName: string;
  files: OfferFile[];
  total: number;
}

export interface ShareError {
  code: string;
  message: string;
}

export type Direction = "send" | "receive";
export type TransferStatus = "running" | "done" | "failed";

export interface Transfer {
  id: string;
  direction: Direction;
  peerName: string;
  done: number;
  total: number;
  bytesPerSec: number;
  file: string;
  status: TransferStatus;
  error: ShareError | null;
  paths: string[];
}

export interface ProgressEvent {
  transferId: string;
  direction: Direction;
  peerName: string;
  done: number;
  total: number;
  bytesPerSec: number;
  file: string;
}

export interface DoneEvent {
  transferId: string;
  direction: Direction;
  peerName: string;
  ok: boolean;
  paths: string[];
  error: ShareError | null;
}

export interface ShareState {
  info: ShareInfo | null;
  peers: readonly Peer[];
  transfers: ReadonlyMap<string, Transfer>;
  offers: readonly Offer[];
}
