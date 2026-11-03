import type { LucideIcon } from "lucide-preact";

export function ToolButton(props: { icon: LucideIcon; label: string; on: boolean; onClick: () => void; title?: string }) {
  const Icon = props.icon;
  return (
    <button type="button" class={props.on ? "ed-tool on" : "ed-tool"} aria-pressed={props.on} title={props.title ?? props.label} onClick={props.onClick}>
      <Icon size={17} /> {props.label}
    </button>
  );
}
