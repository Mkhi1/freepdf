import type { ComponentType } from "preact";

type EditorModule = { default: ComponentType<{ id: string }> };

/**
 * Register finished editors here, one lazy import per tool id.
 * Any tool not listed falls back to the placeholder route.
 */
const EDITORS: Record<string, () => Promise<EditorModule>> = {
  organize: () => import("./organize/Organize"),
  compare: () => import("./compare/Compare"),
  reader: () => import("./reader/Reader"),
  edit: () => import("./edit/EditEditor"),
  sign: () => import("./sign/SignEditor"),
  redact: () => import("./redact/RedactEditor"),
  annotate: () => import("./annotate/AnnotateEditor"),
  crop: () => import("./crop/CropEditor"),
};

export function loadEditor(id: string): Promise<EditorModule> {
  const load = EDITORS[id];
  if (load) return load();
  return import("./EditorPlaceholder").then((m) => ({ default: m.EditorPlaceholder }));
}
