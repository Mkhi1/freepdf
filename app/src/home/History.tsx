import { useMemo, useState } from "preact/hooks";
import { FolderOpen, Search, Trash2, X } from "lucide-preact";
import { isPdf, showInFolder } from "../engine/files";
import { dayGroup, removeEntry, timeAgo, useHistory } from "../state/history";
import type { HistoryEntry } from "../state/history";
import { SendTo } from "../share/SendTo";
import { FileName } from "../ui/FileName";
import { HomeFrame } from "./HomeFrame";
import { actionLabel, confirmClear, openEntry } from "./Recent";

const GROUP_ORDER = ["Today", "Yesterday", "This week", "Earlier"];

function Row({ entry }: { entry: HistoryEntry }) {
  return (
    <li class="hist-row">
      <button type="button" class="hist-main" title={entry.path} onClick={() => openEntry(entry)}>
        <FileName name={entry.name} class="hist-name" />
        <span class="hist-meta">{actionLabel(entry)}, {timeAgo(entry.at).toLowerCase()}</span>
      </button>
      <div class="hist-actions">
        <button type="button" class="btn small" onClick={() => openEntry(entry)}>{isPdf(entry.path) ? "Read" : "Open"}</button>
        <button type="button" class="icon-btn" aria-label="Show in folder" title="Show in folder"
          onClick={() => void showInFolder(entry.path)}><FolderOpen size={16} /></button>
        <SendTo path={entry.path} compact />
        <button type="button" class="icon-btn" aria-label="Remove from history" title="Remove from history"
          onClick={() => removeEntry(entry.path)}><X size={16} /></button>
      </div>
    </li>
  );
}

/** Every file opened or made in the app, newest first. */
export function History() {
  const history = useHistory();
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? history.filter((e) => e.name.toLowerCase().includes(q)) : history;
  }, [history, query]);
  const groups = GROUP_ORDER
    .map((label) => ({ label, items: shown.filter((e) => dayGroup(e.at) === label) }))
    .filter((group) => group.items.length);

  return (
    <HomeFrame active="history">
      <div class="hist-head">
        <div>
          <h1>History</h1>
          <p>Files you opened or made here. This list stays on this computer.</p>
        </div>
        {history.length ? <button type="button" class="btn" onClick={confirmClear}><Trash2 size={15} /> Clear history</button> : null}
      </div>
      {history.length ? (
        <label class="searchbox hist-search">
          <Search size={16} aria-hidden="true" />
          <input type="search" placeholder="Find a file" dir="auto" value={query} onInput={(e) => setQuery(e.currentTarget.value)} />
        </label>
      ) : null}
      {groups.map((group) => (
        <section key={group.label} aria-label={group.label}>
          <h2 class="hist-day">{group.label}</h2>
          <ul class="hist-list">{group.items.map((entry) => <Row key={entry.path} entry={entry} />)}</ul>
        </section>
      ))}
      {!history.length ? <p class="empty">Nothing here yet. Open a PDF and it will show up here.</p> : null}
      {history.length && !shown.length ? <p class="empty">No file matches "{query}".</p> : null}
    </HomeFrame>
  );
}
