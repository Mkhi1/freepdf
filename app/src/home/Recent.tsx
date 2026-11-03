import { FileText, X } from "lucide-preact";
import { isPdf, openFile } from "../engine/files";
import { clearHistory, removeEntry, timeAgo, useHistory, useRecentTools } from "../state/history";
import type { HistoryEntry } from "../state/history";
import { showDocument } from "../state/tabs";
import { getTool } from "../tools/registry";
import type { ToolDef } from "../tools/registry";
import { FileName } from "../ui/FileName";
import { PageImage } from "../ui/PageImage";

const RECENT_COUNT = 12;
const THUMB_WIDTH = 240;
const CLEAR_MESSAGE = "Clear your whole history? Your files stay where they are.";

export function openEntry(entry: HistoryEntry): void {
  if (isPdf(entry.path)) showDocument(entry.path);
  else void openFile(entry.path);
}

export function actionLabel(entry: HistoryEntry): string {
  const tool = entry.toolId ? getTool(entry.toolId) : undefined;
  return tool ? `Made with ${tool.name}` : "Opened";
}

export function confirmClear(): void {
  if (window.confirm(CLEAR_MESSAGE)) clearHistory();
}

function RecentCard({ entry }: { entry: HistoryEntry }) {
  return (
    <div class="recent-card">
      <button type="button" class="recent-open" title={entry.path} onClick={() => openEntry(entry)}>
        <span class="recent-thumb">
          {isPdf(entry.path)
            ? <PageImage file={entry.path} page={0} width={THUMB_WIDTH} bare alt="" />
            : <FileText size={34} strokeWidth={1.5} aria-hidden="true" />}
        </span>
        <FileName name={entry.name} class="recent-name" />
        <span class="recent-meta">{timeAgo(entry.at)}</span>
      </button>
      <button type="button" class="recent-remove" aria-label={`Remove ${entry.name} from history`} title="Remove from history"
        onClick={() => removeEntry(entry.path)}><X size={14} /></button>
    </div>
  );
}

/** The latest files, so getting back to a document takes one click. */
export function RecentFiles() {
  const history = useHistory();
  if (!history.length) return null;
  return (
    <section class="recent" aria-label="Recent files">
      <div class="recent-head">
        <h2>Recent files</h2>
        <button type="button" class="recent-clear" onClick={confirmClear}>Clear all</button>
      </div>
      <div class="recent-row">
        {history.slice(0, RECENT_COUNT).map((entry) => <RecentCard key={entry.path} entry={entry} />)}
      </div>
    </section>
  );
}

function ToolTile({ tool }: { tool: ToolDef }) {
  const Icon = tool.icon;
  return (
    <a class={`tool-tile cat-${tool.category}`} href={`#/tool/${tool.id}`} title={tool.blurb}>
      <span class="card-icon" aria-hidden="true"><Icon size={22} strokeWidth={1.8} /></span>
      <span>{tool.name}</span>
    </a>
  );
}

/** Tools used last, topped up with the common ones so the row is never empty. */
export function RecentTools() {
  const tools = useRecentTools().map(getTool).filter((tool): tool is ToolDef => Boolean(tool));
  return (
    <section class="recent" aria-label="Recent tools">
      <div class="recent-head"><h2>Recent tools</h2></div>
      <div class="tool-tiles">{tools.map((tool) => <ToolTile key={tool.id} tool={tool} />)}</div>
    </section>
  );
}
