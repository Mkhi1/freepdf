import { useEffect, useRef, useState } from "preact/hooks";
import { ArrowUpRight, Circle, Eraser, ImagePlus, Minus, MousePointer2, Pencil, Square, Type } from "lucide-preact";
import { pickFiles } from "../kit";
import { DocGate, EditorShell } from "../canvas/EditorShell";
import { ToolButton } from "../canvas/ToolButton";
import { newId } from "../canvas/types";
import type { DocView, DrawMode, Gesture, PreviewStyle } from "../canvas/types";
import { useEditorDoc } from "../canvas/useEditorDoc";
import { useEditorRun } from "../canvas/useEditorRun";
import { useItemsEditor } from "../canvas/useItemsEditor";
import { imageSrc } from "../../engine/files";
import { EditSidebar } from "./EditSidebar";
import type { StyleKind } from "./EditSidebar";
import { renderEditItem } from "./EditViews";
import {
  applyBox, applyEnd, buildEditArgs, DEFAULT_STYLE, imageItem, inkItem, shapeItem, styleFrom, textItem, whiteoutItem, withStyle,
} from "./items";
import type { EditItem, EditStyle, ShapeKind } from "./items";

type Tool = "select" | "text" | "image" | "ink" | "whiteout" | ShapeKind;

const MODE: Record<Tool, DrawMode> = {
  select: "none", text: "rect", image: "rect", ink: "stroke", whiteout: "rect", rect: "rect", ellipse: "ellipse", line: "line", arrow: "line",
};

function kindOf(tool: Tool): StyleKind {
  if (tool === "select") return "none";
  if (tool === "rect" || tool === "ellipse" || tool === "line" || tool === "arrow") return "shape";
  return tool;
}

function imageAspect(path: string): Promise<number> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 1.5);
    img.onerror = () => resolve(1.5);
    img.src = imageSrc(path);
  });
}

function EditBody({ doc }: { doc: DocView }) {
  const ed = useItemsEditor<EditItem>(doc.sizes, applyBox);
  const run = useEditorRun("edit");
  const [tool, setTool] = useState<Tool>("select");
  const [style, setStyle] = useState<EditStyle>(DEFAULT_STYLE);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [picture, setPicture] = useState<{ path: string; aspect: number } | null>(null);
  const fresh = useRef<string | null>(null);
  const styleSession = useRef<string | null>(null);
  const { history } = ed;

  useEffect(() => {
    if (ed.selected) setStyle((s) => styleFrom(ed.selected!, s));
    styleSession.current = null;
  }, [ed.selectedId]);

  const changeStyle = (patch: Partial<EditStyle>) => {
    const next = { ...style, ...patch };
    setStyle(next);
    if (!ed.selected) return;
    if (styleSession.current !== ed.selected.id) { history.checkpoint(); styleSession.current = ed.selected.id; }
    history.live(history.get().map((i) => (i.id === ed.selectedId ? withStyle(i, next) : i)));
  };

  const choose = async (next: Tool) => {
    setTool(next);
    ed.select(null);
    if (next !== "image") return;
    const [path] = await pickFiles({ accepts: ["png", "jpg", "jpeg", "bmp", "gif", "webp"], multiple: false, title: "Choose a picture" });
    if (!path) { setTool("select"); return; }
    setPicture({ path, aspect: await imageAspect(path) });
  };

  const draw = (g: Gesture) => {
    const id = newId();
    const at = g.type === "click" ? g.pt : g.type === "rect" ? g.start : g.points[0];
    if (tool === "text") {
      ed.add(textItem(id, g.page, at, g.type === "rect" ? g.box : null, style));
      fresh.current = id;
      setEditingId(id);
      setTool("select");
    } else if (tool === "image" && picture) {
      ed.add(imageItem(id, g.page, picture.path, picture.aspect, g.type === "rect" ? g.box : null, at));
      setTool("select");
    } else if (tool === "ink" && g.type === "stroke") {
      ed.add(inkItem(id, g.page, g.points, style), false);
    } else if (tool === "whiteout" && g.type === "rect") {
      ed.add(whiteoutItem(id, g.page, g.box, style));
      setTool("select");
    } else if ((tool === "rect" || tool === "ellipse" || tool === "line" || tool === "arrow") && g.type === "rect") {
      ed.add(shapeItem(id, g.page, tool, g.start, g.end, style));
      setTool("select");
    }
  };

  const setText = (id: string, text: string) => history.live(history.get().map((i) => (i.id === id && i.kind === "text" ? { ...i, text } : i)));
  const editDone = (id: string) => {
    setEditingId(null);
    const item = history.get().find((i) => i.id === id);
    if (item?.kind === "text" && !item.text.trim()) {
      if (fresh.current === id) history.undo(); else ed.remove(id);
    }
    fresh.current = null;
  };

  const preview: PreviewStyle = { stroke: tool === "ink" ? style.color : style.stroke, width: style.width };
  const args = buildEditArgs(doc.file, doc.password, ed.items);
  const count = (args.items as unknown[]).length;
  const visibleKind: StyleKind = ed.selected ? ed.selected.kind : kindOf(tool);

  const tools = (
    <>
      <ToolButton icon={MousePointer2} label="Select" on={tool === "select"} onClick={() => void choose("select")} />
      <ToolButton icon={Type} label="Text" on={tool === "text"} onClick={() => void choose("text")} />
      <ToolButton icon={ImagePlus} label="Image" on={tool === "image"} onClick={() => void choose("image")} />
      <span class="ed-sep" />
      <ToolButton icon={Square} label="Rectangle" on={tool === "rect"} onClick={() => void choose("rect")} />
      <ToolButton icon={Circle} label="Ellipse" on={tool === "ellipse"} onClick={() => void choose("ellipse")} />
      <ToolButton icon={Minus} label="Line" on={tool === "line"} onClick={() => void choose("line")} />
      <ToolButton icon={ArrowUpRight} label="Arrow" on={tool === "arrow"} onClick={() => void choose("arrow")} />
      <span class="ed-sep" />
      <ToolButton icon={Pencil} label="Draw" on={tool === "ink"} onClick={() => void choose("ink")} />
      <ToolButton icon={Eraser} label="Whiteout" on={tool === "whiteout"} onClick={() => void choose("whiteout")} />
    </>
  );

  return (
    <EditorShell<EditItem>
      toolId="edit"
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
      action={{
        label: "Save changes", disabled: count === 0, hint: count === 0 ? "Add something to the page first." : null,
        onClick: () => void run.start("edit", args),
      }}
      sidebar={
        <EditSidebar
          kind={visibleKind}
          style={style}
          onStyle={changeStyle}
          hasSelection={!!ed.selected}
          onDelete={() => ed.selectedId && ed.remove(ed.selectedId)}
          count={count}
        />
      }
      canvas={{
        items: ed.items,
        selectedId: ed.selectedId,
        onSelect: (id) => { ed.select(id); if (id !== editingId) setEditingId(null); },
        onBegin: history.checkpoint,
        onChange: history.live,
        render: (item, ctx) => renderEditItem(item, ctx, { editingId, onText: setText, onEditStart: history.checkpoint, onEditDone: editDone }),
        applyBox,
        applyEnd,
        mode: tool === "image" && !picture ? "none" : MODE[tool],
        preview,
        onDraw: draw,
        onItemDoubleClick: (id) => { if (history.get().find((i) => i.id === id)?.kind === "text") setEditingId(id); },
        cursor: tool === "text" ? "text" : undefined,
      }}
    />
  );
}

export default function EditEditor() {
  const state = useEditorDoc();
  return <DocGate state={state}>{(doc) => <EditBody key={doc.file} doc={doc} />}</DocGate>;
}
