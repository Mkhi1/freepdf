import { useState } from "preact/hooks";
import type { JSX } from "preact";
import "./gate.css";
import { Lock, TriangleAlert } from "lucide-preact";
import { inspect } from "../../state/session";
import type { FileEntry } from "../../state/session";
import { FileName } from "../../ui/FileName";

function Unlock({ file }: { file: FileEntry }) {
  const [text, setText] = useState("");
  const submit = (e: Event) => {
    e.preventDefault();
    if (text) void inspect(file.path, text);
  };
  return (
    <form class="gate-card" onSubmit={submit}>
      <Lock size={26} />
      <FileName name={file.name} class="gate-name" />
      <p>This file is locked. Type its password to open it.</p>
      <input class="input" type="password" dir="ltr" value={text} placeholder="Password" autoFocus
        onInput={(e) => setText(e.currentTarget.value)} />
      {file.error ? <small class="gate-error">{file.error}</small> : null}
      <button type="submit" class="btn primary" disabled={!text}>Unlock</button>
    </form>
  );
}

/** Shows what is blocking the editor, or nothing when every file is ready. */
export function blocker(files: readonly FileEntry[]): JSX.Element | null {
  const bad = files.find((f) => f.status !== "ready");
  if (!bad) return null;
  if (bad.status === "locked") return <div class="gate"><Unlock file={bad} /></div>;
  if (bad.status === "error") {
    return (
      <div class="gate"><div class="gate-card"><TriangleAlert size={26} /><FileName name={bad.name} class="gate-name" /><p>{bad.error}</p>
        <a class="btn" href="#/">Back to all tools</a></div></div>
    );
  }
  return <div class="gate"><span class="gate-wait">Opening your file</span></div>;
}
