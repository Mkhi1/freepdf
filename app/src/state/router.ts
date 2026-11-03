import { useEffect, useState } from "preact/hooks";

export type Route =
  | { name: "home" | "history" | "devices" }
  | { name: "tools"; category: string }
  | { name: "tool" | "work" | "result" | "editor"; id: string };

export function parseHash(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#\/?/, "").split("?");
  const [section, id] = path.split("/");
  if (section === "history") return { name: "history" };
  if (section === "devices") return { name: "devices" };
  if (section === "tools") return { name: "tools", category: new URLSearchParams(query).get("c") ?? "all" };
  if ((section === "tool" || section === "work" || section === "result" || section === "editor") && id) {
    return { name: section, id };
  }
  return { name: "home" };
}

export function go(path: string): void {
  const next = `#/${path}`;
  if (location.hash === next) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = next;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
