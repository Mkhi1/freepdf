import { useState } from "preact/hooks";
import { Highlighter, MousePointer2, Pencil, StickyNote, Strikethrough, Trash2, Type, Underline } from "lucide-preact";
import { ColorField, Group, NumberField } from "../../ui/fields";
import { DocGate, EditorShell } from "../canvas/EditorShell";
import { ItemSvg, smoothPath } from "../canvas/ItemViews";
import { ToolButton } from "../canvas/ToolButton";
import { newId } from "../canvas/types";
import type { DocView, DrawMode, Gesture, RenderContext } from "../canvas/types";
import { useEditorDoc } from "../canvas/useEditorDoc";
import { useEditorRun } from "../canvas/useEditorRun";
import { useItemsEditor } from "../canvas/useItemsEditor";
import { applyBox, buildAnnotateArgs, DEFAULT_COLORS, freeItem, inkAnnot, markItem, stickyItem, withColor } from "./items";
import type { AnnotKind, NoteItem } from "./items";

type Tool = "select" | AnnotKind;

const MODE: Record<Tool, DrawMode> = {
  select: "none", highlight: "rect", underline: "rect", strikeout: "rect", note: "point", ink: "stroke", freetext: "rect",
};

function render(item: NoteItem, ctx: RenderContext) {
  switch (item.kind) {
    case "highlight":
      return <div style={{ position: "absolute", inset: 0, background: item.color, opacity: 0.45, mixBlendMode: "multiply" }} />;
    case "underline":
      return <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: Math.max(1.5, ctx.scale), background: item.color }} />;
    case "strikeout":
      return <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: Math.max(1.5, ctx.scale), background: item.color }} />;
    case "note":
      return <div class="ed-note" style={{ background: item.color }} title={item.text}><StickyNote size={Math.max(12, 14 * ctx.scale * 0.75)} /></div>;
    case "ink":
      return (
        <ItemSvg box={item.box}>
          <path d={smoothPath(item.points)} fill="none" stroke={item.color} stroke-width={item.width} stroke-linecap="round" stroke-linejoin="round" />
        </ItemSvg>
      );
    case "freetext":
      return (
        <div dir="auto" style={{ position: "absolute", inset: 0, color: item.color, fontSize: `${item.size * ctx.scale}px`, lineHeight: 1.25, whiteSpace: "pre-wrap", overflow: "hidden", border: "1px dashed var(--line)", cursor: "move" }}>
          {item.text || <span style={{ opacity: 0.5 }}>Type in the box on the right</span>}
        </div>
      );
  }
}

function AnnotBody({ doc }: { doc: DocView }) {
  const ed = useItemsEditor<NoteItem>(doc.sizes, applyBox);
  const run = useEditorRun("annotate");
  const [tool, setTool] = useState<Tool>("select");
  const [colors, setColors] = useState(DEFAULT_COLORS);
  const [width, setWidth] = useState(2);
  const [size, setSize] = useState(14);
  const { history } = ed;
  const kind: AnnotKind | null = ed.selected ? ed.selected.kind : tool === "select" ? null : tool;

  const pick = (next: Tool) => { setTool(next); ed.select(null); };

  const draw = (g: Gesture) => {
    const id = newId();
    const color = colors[tool as AnnotKind];
    if (g.type === "stroke" && tool === "ink") ed.add(inkAnnot(id, g.page, g.points, color, width), false);
    else if (tool === "note" && g.type === "click") { ed.add(stickyItem(id, g.page, g.pt, color)); setTool("select"); }
    else if (tool === "freetext") { ed.add(freeItem(id, g.page, g.type === "click" ? g.pt : g.type === "rect" ? g.start : g.points[0], g.type === "rect" ? g.box : null, color, size)); setTool("select"); }
    else if ((tool === "highlight" || tool === "underline" || tool === "strikeout") && g.type === "rect" && g.box.w > 3 && g.box.h > 2) {
      ed.add(markItem(id, g.page, tool, g.box, color), false);
    }
  };

  const setColor = (color: string) => {
    if (!kind) return;
    setColors((c) => ({ ...c, [kind]: color }));
    if (ed.selected) ed.patch(ed.selected.id, (i) => withColor(i, color));
  };

  const args = buildAnnotateArgs(doc.file, doc.password, ed.items);
  const count = (args.items as unknown[]).length;
  const textual = ed.selected && (ed.selected.kind === "note" || ed.selected.kind === "freetext") ? ed.selected : null;

  const tools = (
    <>
      <ToolButton icon={MousePointer2} label="Select" on={tool === "select"} onClick={() => pick("select")} />
      <span class="ed-sep" />
      <ToolButton icon={Highlighter} label="Highlight" on={tool === "highlight"} onClick={() => pick("highlight")} />
      <ToolButton icon={Underline} label="Underline" on={tool === "underline"} onClick={() => pick("underline")} />
      <ToolButton icon={Strikethrough} label="Strikeout" on={tool === "strikeout"} onClick={() => pick("strikeout")} />
      <span class="ed-sep" />
      <ToolButton icon={StickyNote} label="Note" on={tool === "note"} onClick={() => pick("note")} />
      <ToolButton icon={Pencil} label="Draw" on={tool === "ink"} onClick={() => pick("ink")} />
      <ToolButton icon={Type} label="Free text" on={tool === "freetext"} onClick={() => pick("freetext")} />
    </>
  );

  const sidebar = (
    <>
      <p class="hint">
        {tool === "select" && !ed.selected ? "Pick a tool above. To mark text, drag over the words you want. Saved as real PDF annotations that other readers can see." : null}
        {tool === "note" ? "Click where the note should sit, then type its text here." : null}
        {tool === "freetext" ? "Drag a box on the page, then type its text here." : null}
        {tool === "ink" ? "Draw with the mouse." : null}
        {tool === "highlight" || tool === "underline" || tool === "strikeout" ? "Drag over the words. Tip: keep the box to one line." : null}
      </p>
      {kind ? (
        <Group title="Style">
          <ColorField label="Colour" value={colors[kind]} onChange={setColor} />
          {kind === "ink" ? <NumberField label="Thickness" value={width} min={1} max={20} unit="pt" onChange={(w) => { setWidth(w); if (ed.selected?.kind === "ink") ed.patch(ed.selected.id, (i) => ({ ...i, width: w }) as NoteItem); }} /> : null}
          {kind === "freetext" ? <NumberField label="Text size" value={ed.selected?.kind === "freetext" ? ed.selected.size : size} min={6} max={72} unit="pt" onChange={(s) => { setSize(s); if (ed.selected?.kind === "freetext") ed.patch(ed.selected.id, (i) => ({ ...i, size: s }) as NoteItem); }} /> : null}
        </Group>
      ) : null}
      {textual ? (
        <Group title={textual.kind === "note" ? "Note text" : "Text"}>
          <textarea class="ed-textarea" dir="auto" aria-label="Text" value={textual.text} placeholder="Type here" onFocus={history.checkpoint} onInput={(e) => history.live(history.get().map((i) => (i.id === textual.id ? ({ ...i, text: e.currentTarget.value } as NoteItem) : i)))} />
        </Group>
      ) : null}
      <Group title="Selected item">
        <button type="button" class="btn small" disabled={!ed.selected} onClick={() => ed.selectedId && ed.remove(ed.selectedId)}><Trash2 size={15} /> Delete</button>
      </Group>
      <p class="hint">{count === 0 ? "Nothing added yet." : `${count} ${count === 1 ? "annotation" : "annotations"} will be saved.`}</p>
    </>
  );

  return (
    <EditorShell<NoteItem>
      toolId="annotate"
      doc={doc}
      page={ed.page}
      onPage={ed.setPage}
      counts={ed.counts}
      tools={tools}
      canUndo={history.canUndo}
      canRedo={history.canRedo}
      onUndo={history.undo}
      onRedo={history.redo}
      run={run}
      action={{ label: "Save changes", disabled: count === 0, hint: count === 0 ? "Add an annotation first." : null, onClick: () => void run.start("annotate", args) }}
      sidebar={sidebar}
      canvas={{
        items: ed.items,
        selectedId: ed.selectedId,
        onSelect: ed.select,
        onBegin: history.checkpoint,
        onChange: history.live,
        render,
        applyBox,
        mode: MODE[tool],
        onDraw: draw,
        itemsFirst: tool === "note" || tool === "freetext" || tool === "select",
        preview: { stroke: tool === "ink" ? colors.ink : colors[tool === "select" ? "highlight" : tool], width },
      }}
    />
  );
}

export default function AnnotateEditor() {
  const state = useEditorDoc();
  return <DocGate state={state}>{(doc) => <AnnotBody key={doc.file} doc={doc} />}</DocGate>;
}
