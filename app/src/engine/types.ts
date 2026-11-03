export interface EngineOutput {
  path: string;
  size?: number;
}

export interface EngineResult {
  outputs: EngineOutput[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  summary: Record<string, any>;
}

export interface Progress {
  id: string;
  value: number;
  message?: string;
}

export type ProgressHandler = (progress: Progress) => void;

/** Thrown by engine calls. The message is written for the user. */
export class EngineFailure extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export interface PdfInfo {
  pages: number;
  sizes: Array<[number, number]>;
  encrypted: boolean;
  needs_password: boolean;
  scanned: boolean;
  title: string;
  bytes: number;
}
