import { useEffect } from "preact/hooks";
import { ArrowRight, BookOpen, CircleCheck, ExternalLink, FolderOpen } from "lucide-preact";
import { inTauri } from "../engine/client";
import { fileExt, formatBytes, fileName, isPdf, openFile, showInFolder } from "../engine/files";
import type { EngineOutput } from "../engine/types";
import { go } from "../state/router";
import { factFor } from "./facts";
import { clearFiles, setDone, setFiles, useSession } from "../state/session";
import { getTool, nextTools, toolRoute } from "../tools/registry";
import type { ToolDef } from "../tools/registry";
import { NotFound } from "../tools/ToolPage";
import { FileName } from "../ui/FileName";

function headline(count: number): string {
  if (count > 1) return `Done. ${count} files are ready.`;
  return count === 1 ? "Done. Your file is ready." : "Done.";
}

function Facts({ tool, summary }: { tool: ToolDef; summary: Record<string, unknown> }) {
  const fact = factFor(tool.id, summary);
  if (!fact) return null;
  return (
    <p class="facts">
      {fact.lead ? <b>{fact.lead}</b> : null}
      {fact.text}
    </p>
  );
}

function readHere(path: string): void {
  setFiles([path]);
  go("editor/reader");
}

function OutputRow({ output }: { output: EngineOutput }) {
  const pdf = isPdf(output.path);
  return (
    <li class="out">
      <div class="out-info">
        <FileName name={fileName(output.path)} class="out-name" />
        <span class="out-meta">{fileExt(output.path).toUpperCase()}{output.size ? ` · ${formatBytes(output.size)}` : ""}</span>
      </div>
      <div class="out-actions">
        {pdf ? <button type="button" class="btn primary" onClick={() => readHere(output.path)}><BookOpen size={16} /> Open in reader</button> : null}
        <button type="button" class={pdf ? "btn" : "btn primary"} onClick={() => void openFile(output.path)}><ExternalLink size={16} /> {pdf ? "Open in other app" : "Open"}</button>
        <button type="button" class="btn" onClick={() => void showInFolder(output.path)}><FolderOpen size={16} /> Show in folder</button>
      </div>
    </li>
  );
}

export function Result({ id }: { id: string }) {
  const tool = getTool(id);
  const { done } = useSession();

  useEffect(() => {
    if (inTauri || done) return;
    void import("../engine/mock").then(async (m) => setDone({ toolId: id, result: await m.mockCall("compress", {}) }));
  }, [id]);

  if (!tool) return <NotFound />;
  if (!done) return null;
  const { outputs, summary } = done.result;
  const text = typeof summary.text === "string" ? summary.text : "";
  const allPdf = outputs.length > 0 && outputs.every((o) => isPdf(o.path));

  const useNext = (next: ToolDef) => {
    setFiles(outputs.map((o) => o.path).slice(0, next.max ?? outputs.length));
    go(toolRoute(next));
  };
  const again = () => {
    clearFiles();
    go(`tool/${tool.id}`);
  };

  return (
    <div class="page">
      <main class="resultpage">
        <span class="done-mark" aria-hidden="true"><CircleCheck size={40} strokeWidth={1.6} /></span>
        <h1>{headline(outputs.length)}</h1>
        <Facts tool={tool} summary={summary} />
        {outputs.length ? <ul class="outs">{outputs.map((o) => <OutputRow output={o} />)}</ul> : null}
        {text ? <pre class="summary-text" dir="auto">{text}</pre> : null}

        {allPdf ? (
          <section class="next" aria-label="Next tools">
            <h2>Keep going with this file</h2>
            <div class="next-list">
              {nextTools(tool.id).map((next) => {
                const Icon = next.icon;
                return (
                  <button type="button" class={`next-card cat-${next.category}`} onClick={() => useNext(next)}>
                    <span class="card-icon"><Icon size={18} /></span>
                    <span class="next-name">{next.name}</span>
                    <ArrowRight size={16} class="next-arrow" />
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        <div class="result-foot">
          <button type="button" class="btn" onClick={again}>Start over with this tool</button>
          <a class="btn" href="#/">All tools</a>
        </div>
      </main>
    </div>
  );
}
