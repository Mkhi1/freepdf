import { useState } from "preact/hooks";
import { FilePlus, Globe, ScanLine } from "lucide-preact";
import { pickFiles } from "../engine/files";
import { go } from "../state/router";
import { clearFiles, setFiles } from "../state/session";
import { useWindowDrop } from "../ui/useDrop";
import { getTool, toolRoute } from "./registry";
import type { ToolDef } from "./registry";

function kindLabel(tool: ToolDef): string {
  if (tool.accepts.length === 0) return "files";
  if (tool.accepts.length === 1 && tool.accepts[0] === "pdf") return "PDF files";
  return `${tool.accepts.slice(0, 4).join(", ").toUpperCase()} files`;
}

export function ToolPage({ id }: { id: string }) {
  const tool = getTool(id);
  const [busy, setBusy] = useState(false);
  const accepts = tool?.accepts ?? [];

  const start = (paths: string[]) => {
    if (!tool) return;
    setFiles(tool.max === null ? paths : paths.slice(0, tool.max));
    go(toolRoute(tool));
  };
  const drop = useWindowDrop(accepts, start);

  if (!tool) return <NotFound />;
  const Icon = tool.icon;
  const takesFiles = tool.max !== 0;
  const plural = tool.max === null || tool.max > 1;

  const choose = async () => {
    setBusy(true);
    try {
      const paths = await pickFiles({ accepts: tool.accepts, multiple: plural, title: `Choose ${kindLabel(tool)}` });
      if (paths.length) start(paths);
    } finally {
      setBusy(false);
    }
  };

  const withoutFiles = () => {
    clearFiles();
    go(toolRoute(tool));
  };

  return (
    <div class={drop.hovering ? "page dragging" : "page"}>
      <main class="toolpage">
        <a class="back" href="#/">All tools</a>
        <span class={`hero-icon cat-${tool.category}`} aria-hidden="true"><Icon size={34} strokeWidth={1.6} /></span>
        <h1>{tool.name}</h1>
        <p class="lead">{tool.blurb}</p>

        <div class="dropzone">
          {takesFiles ? (
            <>
              <button type="button" class="btn big primary" disabled={busy} onClick={() => void choose()}>
                <FilePlus size={22} /> {plural ? `Select ${kindLabel(tool)}` : `Select a ${tool.accepts.length === 1 && tool.accepts[0] === "pdf" ? "PDF file" : "file"}`}
              </button>
              <p class="drop-or">or drop {plural ? "them" : "it"} anywhere in this window</p>
            </>
          ) : null}
          {tool.id === "html_to_pdf" ? (
            <button type="button" class="btn big" onClick={withoutFiles}><Globe size={20} /> Enter a web address</button>
          ) : null}
          {tool.id === "scan_to_pdf" ? (
            <button type="button" class="btn big primary" onClick={withoutFiles}><ScanLine size={20} /> Choose a scanner</button>
          ) : null}
          {tool.min > 1 ? <p class="drop-note">Pick at least {tool.min} files.</p> : null}
        </div>
        {drop.notice ? <p class="notice" role="status">{drop.notice}</p> : null}
        {drop.hovering ? <div class="drop-veil"><span>Drop to start</span></div> : null}
      </main>
    </div>
  );
}

export function NotFound() {
  return (
    <div class="page">
      <main class="toolpage">
        <h1>That tool is not here</h1>
        <p class="lead">Go back and pick one from the list.</p>
        <a class="btn primary" href="#/">All tools</a>
      </main>
    </div>
  );
}
