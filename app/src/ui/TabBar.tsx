import { FileText, Home, Plus, X } from "lucide-preact";
import { pickFiles } from "../engine/files";
import { go } from "../state/router";
import type { Route } from "../state/router";
import { useSession } from "../state/session";
import { closeTab, mayLeave, openDocuments, showDocument, useTabs } from "../state/tabs";
import { FileName } from "./FileName";
import "./tabbar.css";

function isHome(route: Route): boolean {
  return route.name === "home" || route.name === "tools" || route.name === "history" || route.name === "devices";
}

function goHome(): void {
  if (mayLeave()) go("");
}

async function addFiles(): Promise<void> {
  const paths = await pickFiles({ accepts: ["pdf"], multiple: true, title: "Open PDF files" });
  if (paths.length && mayLeave()) openDocuments(paths);
}

/** The bar above every screen: home, one tab per open PDF, and a button to open more. */
export function TabBar({ route }: { route: Route }) {
  const tabs = useTabs();
  const { files } = useSession();
  const reading = route.name === "editor" && route.id === "reader";
  const current = reading ? files[0]?.path : undefined;

  const select = (path: string) => {
    if (path !== current && mayLeave()) showDocument(path);
  };
  const close = (path: string) => {
    const active = path === current;
    if (!active || mayLeave()) closeTab(path, active);
  };

  return (
    <header class="tabbar">
      <img class="tabbar-logo" src="./logo.svg" alt="Free PDF" />
      <nav class="tabs" aria-label="Open files">
        <button type="button" class={isHome(route) ? "tab home-tab on" : "tab home-tab"} onClick={goHome}>
          <Home size={15} aria-hidden="true" /> Home
        </button>
        {tabs.map((tab) => (
          <div key={tab.path} class={tab.path === current ? "tab on" : "tab"} title={tab.path}>
            <button type="button" class="tab-open" onClick={() => select(tab.path)}>
              <FileText size={15} aria-hidden="true" />
              <FileName name={tab.name} class="tab-name" />
            </button>
            <button type="button" class="tab-close" aria-label={`Close ${tab.name}`} onClick={() => close(tab.path)}><X size={14} /></button>
          </div>
        ))}
        <button type="button" class="tab-add" aria-label="Open a PDF" title="Open a PDF" onClick={() => void addFiles()}><Plus size={17} /></button>
      </nav>
    </header>
  );
}
