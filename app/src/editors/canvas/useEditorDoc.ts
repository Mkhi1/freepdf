import { useEffect, useState } from "preact/hooks";
import { getInfo, inTauri } from "../../engine/client";
import { addFiles, useSession } from "../../state/session";
import type { FileEntry } from "../../state/session";
import type { DocView } from "./types";

export type DocState =
  | { status: "empty" }
  | { status: "loading"; file: FileEntry }
  | { status: "error"; message: string }
  | { status: "ready"; file: FileEntry; doc: DocView };

/** The first chosen PDF with its page sizes. Browser previews open a sample file by themselves. */
export function useEditorDoc(): DocState {
  const { files } = useSession();
  const file = files[0];
  const [loaded, setLoaded] = useState<{ path: string; doc: DocView } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (inTauri || file) return;
    void import("../../engine/mock").then((m) => addFiles(m.mockPick(["pdf"], false), 1));
  }, [file === undefined]);

  useEffect(() => {
    if (!file || file.status !== "ready") return;
    let alive = true;
    setProblem(null);
    getInfo(file.path, file.password)
      .then((info) => {
        if (!alive) return;
        const sizes = info.sizes.map(([w, h]) => ({ w, h }));
        setLoaded({ path: file.path, doc: { file: file.path, password: file.password, sizes } });
      })
      .catch((e: { message?: string }) => alive && setProblem(e.message ?? "This file could not be read."));
    return () => { alive = false; };
  }, [file?.path, file?.status]);

  if (!file) return { status: "empty" };
  if (file.status === "locked") return { status: "error", message: "This file has a password. Remove the password first, then edit it." };
  if (file.status === "error") return { status: "error", message: file.error ?? "This file could not be read." };
  if (problem) return { status: "error", message: problem };
  if (loaded && loaded.path === file.path && loaded.doc.sizes.length) return { status: "ready", file, doc: loaded.doc };
  return { status: "loading", file };
}
