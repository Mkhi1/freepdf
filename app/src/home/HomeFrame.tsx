import type { ComponentChildren } from "preact";
import { Clock, History, Wrench } from "lucide-preact";
import "./recent.css";

const LINKS = [
  { id: "recents", label: "Recents", href: "#/", icon: Clock },
  { id: "tools", label: "Tools", href: "#/tools", icon: Wrench },
  { id: "history", label: "History", href: "#/history", icon: History },
] as const;

export interface HomeFrameProps {
  active: "recents" | "tools" | "history";
  dragging?: boolean;
  children: ComponentChildren;
}

/** The left menu shared by the three home views. */
export function HomeFrame({ active, dragging, children }: HomeFrameProps) {
  return (
    <div class={dragging ? "page homeframe dragging" : "page homeframe"}>
      <nav class="sidemenu" aria-label="Home">
        {LINKS.map(({ id, label, href, icon: Icon }) => (
          <a key={id} href={href} class={active === id ? "on" : ""} aria-current={active === id ? "page" : undefined}>
            <Icon size={17} aria-hidden="true" /> {label}
          </a>
        ))}
        <p class="sidemenu-note">Free, with every tool included. Works offline, and your files stay on this computer.</p>
      </nav>
      <main class="homepane">{children}</main>
    </div>
  );
}
