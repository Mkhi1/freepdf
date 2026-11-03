import { useMemo, useState } from "preact/hooks";
import { Search } from "lucide-preact";
import { CATEGORIES, TOOLS, categoryLabel } from "../tools/registry";
import type { ToolDef } from "../tools/registry";
import { HomeFrame } from "./HomeFrame";

function ToolCard({ tool }: { tool: ToolDef }) {
  const Icon = tool.icon;
  return (
    <a class={`card cat-${tool.category}`} href={`#/tool/${tool.id}`}>
      <span class="card-icon" aria-hidden="true">
        <Icon size={22} strokeWidth={1.8} />
      </span>
      <span class="card-text">
        <span class="card-name">{tool.name}</span>
        <span class="card-blurb">{tool.blurb}</span>
      </span>
    </a>
  );
}

function matches(tool: ToolDef, query: string): boolean {
  const q = query.trim().toLowerCase();
  return !q || `${tool.name} ${tool.blurb} ${categoryLabel(tool.category)}`.toLowerCase().includes(q);
}

/** Every tool, with category filters and search. */
export function Tools({ category }: { category: string }) {
  const [query, setQuery] = useState("");
  const shown = useMemo(
    () => TOOLS.filter((t) => (category === "all" || t.category === category) && matches(t, query)),
    [category, query],
  );

  return (
    <HomeFrame active="tools">
      <div class="tools-head">
        <h1>Tools</h1>
        <label class="searchbox">
          <Search size={16} aria-hidden="true" />
          <input type="search" placeholder="Find a tool" value={query} onInput={(e) => setQuery(e.currentTarget.value)} />
        </label>
      </div>
      <div class="filters" role="tablist" aria-label="Filter tools">
        <a role="tab" aria-selected={category === "all"} class={category === "all" ? "filter on" : "filter"} href="#/tools">All</a>
        {CATEGORIES.map((c) => (
          <a role="tab" aria-selected={category === c.id} class={category === c.id ? "filter on" : "filter"} href={`#/tools?c=${c.id}`}>
            {c.label}
          </a>
        ))}
      </div>
      {shown.length ? (
        <div class="grid">{shown.map((tool) => <ToolCard tool={tool} />)}</div>
      ) : (
        <p class="empty">No tool matches "{query}". Try a shorter word, like merge or word.</p>
      )}
    </HomeFrame>
  );
}
