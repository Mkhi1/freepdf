import { Search } from "lucide-preact";
import { CATEGORIES } from "../tools/registry";
import { go } from "../state/router";

export interface TopBarProps {
  category?: string;
  query?: string;
  onQuery?: (value: string) => void;
}

export function TopBar({ category, query, onQuery }: TopBarProps) {
  return (
    <header class="topbar">
      <a class="logo" href="#/" aria-label="Free PDF, all tools">
        <img src="./logo.svg" alt="Free PDF" height="26" />
      </a>
      <nav class="topnav" aria-label="Categories">
        <a href="#/" class={category === "all" ? "on" : ""}>All tools</a>
        {CATEGORIES.map((c) => (
          <a href={`#/?c=${c.id}`} class={category === c.id ? "on" : ""}>{c.label}</a>
        ))}
        <a href="#/history" class={category === "history" ? "on" : ""}>History</a>
      </nav>
      {onQuery ? (
        <label class="searchbox">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            placeholder="Find a tool"
            value={query ?? ""}
            onInput={(e) => onQuery(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Escape") go(""); }}
          />
        </label>
      ) : (
        <span class="topbar-note">Works offline. Files stay on this computer.</span>
      )}
    </header>
  );
}
