/** File name in a left-to-right box so the extension stays on the right, even for Arabic names. */
export function FileName({ name, class: className }: { name: string; class?: string }) {
  return (
    <span class={className ? `fname ${className}` : "fname"} dir="ltr" title={name}>
      {name}
    </span>
  );
}
