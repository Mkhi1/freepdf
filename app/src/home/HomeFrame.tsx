import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";
import { inTauri } from "../engine/client";
import { Clock, History, MonitorSmartphone, Wrench } from "lucide-preact";
import "./recent.css";

const LINKS = [
  { id: "recents", label: "Recents", href: "#/", icon: Clock },
  { id: "tools", label: "Tools", href: "#/tools", icon: Wrench },
  { id: "history", label: "History", href: "#/history", icon: History },
  { id: "devices", label: "Devices", href: "#/devices", icon: MonitorSmartphone },
] as const;

export interface HomeFrameProps {
  active: "recents" | "tools" | "history" | "devices";
  dragging?: boolean;
  children: ComponentChildren;
}

/** The left menu shared by the home views. */
let versionCache: Promise<string> | null = null;

/** The installed version, read once. */
function appVersion(): Promise<string> {
  if (!inTauri) return Promise.resolve("");
  versionCache ??= import("@tauri-apps/api/app").then((m) => m.getVersion()).catch(() => "");
  return versionCache;
}

export function HomeFrame({ active, dragging, children }: HomeFrameProps) {
  const [version, setVersion] = useState("");
  useEffect(() => {
    void appVersion().then(setVersion);
  }, []);
  return (
    <div class={dragging ? "page homeframe dragging" : "page homeframe"}>
      <nav class="sidemenu" aria-label="Home">
        {LINKS.map(({ id, label, href, icon: Icon }) => (
          <a key={id} href={href} class={active === id ? "on" : ""} aria-current={active === id ? "page" : undefined}>
            <Icon size={17} aria-hidden="true" /> {label}
          </a>
        ))}
        <p class="sidemenu-note">
          Free, with every tool included. Works offline, and your files stay on this computer.
          <span class="sidemenu-credit">Developed by MK{version ? ` · v${version}` : ""}</span>
        </p>
      </nav>
      <main class="homepane">{children}</main>
    </div>
  );
}
