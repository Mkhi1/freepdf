import type { JSX } from "preact";
import type { FileEntry } from "../state/session";

// Option values are plain data that go straight into engine args.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Opts = Record<string, any>;

export interface FormCtx {
  files: readonly FileEntry[];
  reorder: (files: readonly FileEntry[]) => void;
}

export interface FormProps {
  value: Opts;
  set: (patch: Opts) => void;
  ctx: FormCtx;
}

export interface FormSpec {
  defaults: Opts;
  Form: (props: FormProps) => JSX.Element | null;
  toArgs: (opts: Opts, files: readonly FileEntry[]) => Record<string, unknown>;
  /** Returns a sentence to show when the options cannot be used yet. */
  check?: (opts: Opts, files: readonly FileEntry[]) => string | null;
}

export type FormMap = Record<string, FormSpec>;
