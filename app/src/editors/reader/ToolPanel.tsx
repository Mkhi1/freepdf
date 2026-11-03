import { useState } from "preact/hooks";
import { ChevronDown, ChevronRight, PanelRightClose, PanelRightOpen } from "lucide-preact";
import { go } from "../../state/router";
import { getTool, toolRoute } from "../../tools/registry";
import type { ToolId } from "../../tools/registry";
import "./toolpanel.css";

const OPEN_KEY = "freepdf.reader.toolpanel";

const GROUPS: ReadonlyArray<{ label: string; tools: ReadonlyArray<[ToolId, string]> }> = [
  { label: "Convert from PDF", tools: [["pdf_to_images", "PDF to JPG"], ["pdf_to_word", "PDF to Word"], ["pdf_to_ppt", "PDF to PowerPoint"], ["pdf_to_excel", "PDF to Excel"], ["pdf_to_text", "PDF to text"], ["pdfa", "PDF to PDF/A"]] },
  { label: "Edit PDF", tools: [["edit", "Edit PDF"], ["sign", "Sign PDF"], ["rotate", "Rotate PDF"], ["page_numbers", "Page numbers"], ["watermark", "Watermark"], ["crop", "Crop PDF"], ["redact", "Redact PDF"]] },
  { label: "Optimize PDF", tools: [["compress", "Compress PDF"], ["repair", "Repair PDF"], ["ocr", "Recognize text"]] },
  { label: "Organize PDF", tools: [["merge", "Merge PDF"], ["split", "Split PDF"], ["organize", "Organize pages"], ["compare", "Compare PDF"]] },
  { label: "Security", tools: [["protect", "Protect PDF"], ["unlock", "Unlock PDF"]] },
  { label: "Language", tools: [["translate", "Translate PDF"], ["summarize", "Summarize PDF"]] },
];

function startsOpen(): boolean {
  try {
    return localStorage.getItem(OPEN_KEY) !== "closed";
  } catch {
    return true;
  }
}

function remember(open: boolean): void {
  try {
    localStorage.setItem(OPEN_KEY, open ? "open" : "closed");
  } catch {
    // Storage can be blocked. The panel then starts open next time.
  }
}

function ToolButton({ id, label, open, onPick }: { id: ToolId; label: string; open: boolean; onPick: (id: ToolId) => void }) {
  const tool = getTool(id);
  if (!tool) return null;
  const Icon = tool.icon;
  return (
    <button type="button" class={`rd-panel-tool cat-${tool.category}`} title={open ? tool.blurb : label} aria-label={label} onClick={() => onPick(id)}>
      <span class="rd-panel-icon" aria-hidden="true"><Icon size={15} strokeWidth={1.9} /></span>
      {open ? <span class="rd-panel-label">{label}</span> : null}
    </button>
  );
}

/** Every tool beside the open document. One click carries this file into the tool. */
export function ToolPanel({ canLeave }: { canLeave: () => boolean }) {
  const [open, setOpen] = useState(startsOpen);
  const [folded, setFolded] = useState<readonly string[]>([]);
  const toggle = () => {
    remember(!open);
    setOpen(!open);
  };
  const fold = (label: string) => {
    setFolded(folded.includes(label) ? folded.filter((l) => l !== label) : [...folded, label]);
  };
  const pick = (id: ToolId) => {
    const tool = getTool(id);
    if (tool && canLeave()) go(toolRoute(tool));
  };
  return (
    <aside class={open ? "rd-panel" : "rd-panel closed"} aria-label="Tools for this file">
      <button type="button" class="rd-panel-toggle" onClick={toggle} aria-label={open ? "Collapse tools" : "Expand tools"} aria-expanded={open}>
        {open ? <PanelRightClose size={17} aria-hidden="true" /> : <PanelRightOpen size={17} aria-hidden="true" />}
        {open ? <span>Tools</span> : null}
      </button>
      {GROUPS.map((group) => {
        const hidden = open && folded.includes(group.label);
        return (
          <section key={group.label} class="rd-panel-group" aria-label={group.label}>
            {open ? (
              <button type="button" class="rd-panel-head" aria-expanded={!hidden} onClick={() => fold(group.label)}>
                <span>{group.label}</span>
                {hidden ? <ChevronRight size={15} aria-hidden="true" /> : <ChevronDown size={15} aria-hidden="true" />}
              </button>
            ) : null}
            {hidden ? null : group.tools.map(([id, label]) => <ToolButton key={id} id={id} label={label} open={open} onPick={pick} />)}
          </section>
        );
      })}
    </aside>
  );
}
