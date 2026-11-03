import { Hammer } from "lucide-preact";
import { getTool } from "../tools/registry";
import { FileName } from "../ui/FileName";
import { useSession } from "../state/session";

/**
 * PLACEHOLDER route for the visual editors (edit, sign, redact, crop, organize, annotate, compare).
 * To build one: add a component in this folder and register it in editors/index.ts.
 * The chosen files are in the session store (useSession().files); use the helpers from ./kit.
 */
export function EditorPlaceholder({ id }: { id: string }) {
  const tool = getTool(id);
  const { files } = useSession();
  return (
    <div class="page">
      <main class="toolpage">
        <span class="hero-icon" aria-hidden="true"><Hammer size={32} strokeWidth={1.6} /></span>
        <h1>{tool?.name ?? "Editor"} is coming soon</h1>
        <p class="lead">The visual editor for this tool is not built yet. Your files are ready for it.</p>
        {files.length ? (
          <ul class="plain-list">
            {files.map((f) => <li><FileName name={f.name} /></li>)}
          </ul>
        ) : null}
        <a class="btn primary" href="#/">Back to all tools</a>
      </main>
    </div>
  );
}
