import { useState } from "preact/hooks";
import { Crop, RotateCcw } from "lucide-preact";
import { Choices, Group, NumberField } from "../../ui/fields";
import { DocGate, EditorShell } from "../canvas/EditorShell";
import { fitInside, round2, toRect } from "../canvas/geometry";
import type { Box, Size } from "../canvas/geometry";
import type { DocView, Gesture, Item } from "../canvas/types";
import { useEditorDoc } from "../canvas/useEditorDoc";
import { useEditorKeys } from "../canvas/useEditorKeys";
import { useEditorRun } from "../canvas/useEditorRun";
import { useHistory } from "../canvas/useHistory";

type Scope = "page" | "all";
const MM_PER_PT = 25.4 / 72;
const MIN_SIDE = 12;

function startBox(page: Size): Box {
  const m = Math.min(page.w, page.h) * 0.08;
  return { x: m, y: m, w: page.w - 2 * m, h: page.h - 2 * m };
}

function EdgeFields(props: { box: Box; page: Size; onBox: (b: Box) => void }) {
  const { box: b, page } = props;
  const set = (edge: "left" | "top" | "right" | "bottom", value: number) => {
    const x1 = b.x + b.w;
    const y1 = b.y + b.h;
    const next = { left: [value, b.y, x1, y1], top: [b.x, value, x1, y1], right: [b.x, b.y, value, y1], bottom: [b.x, b.y, x1, value] }[edge];
    const [x0, y0, X1, Y1] = next;
    const box = { x: Math.min(x0, X1 - MIN_SIDE), y: Math.min(y0, Y1 - MIN_SIDE), w: 0, h: 0 };
    box.w = Math.max(X1 - box.x, MIN_SIDE);
    box.h = Math.max(Y1 - box.y, MIN_SIDE);
    props.onBox(fitInside(box, page));
  };
  return (
    <div class="ed-numgrid">
      <NumberField label="Left" value={round2(b.x)} min={0} max={page.w} unit="pt" onChange={(v) => set("left", v)} />
      <NumberField label="Top" value={round2(b.y)} min={0} max={page.h} unit="pt" onChange={(v) => set("top", v)} />
      <NumberField label="Right" value={round2(b.x + b.w)} min={0} max={page.w} unit="pt" onChange={(v) => set("right", v)} />
      <NumberField label="Bottom" value={round2(b.y + b.h)} min={0} max={page.h} unit="pt" onChange={(v) => set("bottom", v)} />
    </div>
  );
}

function CropBody({ doc }: { doc: DocView }) {
  const history = useHistory<Box>(startBox(doc.sizes[0]));
  const run = useEditorRun("crop");
  const [page, setPage] = useState(0);
  const [scope, setScope] = useState<Scope>("page");
  const [selected, setSelected] = useState<string | null>("crop");
  const size = doc.sizes[page];
  const box = fitInside(history.value, size);

  useEditorKeys({ onDelete: () => undefined, onUndo: history.undo, onRedo: history.redo, onEscape: () => undefined });

  const item: Item = { id: "crop", page, box, minSize: MIN_SIDE };
  const draw = (g: Gesture) => {
    if (g.type === "rect" && g.box.w >= MIN_SIDE && g.box.h >= MIN_SIDE) history.push(g.box);
  };
  const args = {
    file: doc.file, ...(doc.password ? { password: doc.password } : {}),
    box: toRect(box), ...(scope === "page" ? { pages: [page] } : {}),
  };
  const full = box.w >= size.w - 0.5 && box.h >= size.h - 0.5;

  const sidebar = (
    <>
      <p class="hint">Drag the handles, or drag a new box on the page. Everything outside the box is trimmed away.</p>
      <Group title="Apply to">
        <Choices compact value={scope} onChange={setScope} options={[{ value: "page", label: `Page ${page + 1}` }, { value: "all", label: "All pages" }]} />
        {scope === "all" ? <small class="field-hint">The same box is used on every page. Pages smaller than the box are trimmed to their own edges.</small> : null}
      </Group>
      <Group title="Size">
        <p class="hint" aria-live="polite">
          <b>{Math.round(box.w)} x {Math.round(box.h)} pt</b>{" "}
          ({(box.w * MM_PER_PT).toFixed(0)} x {(box.h * MM_PER_PT).toFixed(0)} mm) of {Math.round(size.w)} x {Math.round(size.h)} pt
        </p>
        <EdgeFields box={box} page={size} onBox={history.push} />
        <button type="button" class="btn small" onClick={() => history.push(startBox(size))}><RotateCcw size={14} /> Reset box</button>
      </Group>
    </>
  );

  return (
    <EditorShell<Item>
      toolId="crop"
      doc={doc}
      page={page}
      onPage={setPage}
      counts={doc.sizes.map(() => 0)}
      tools={<span class="hint"><Crop size={15} style={{ verticalAlign: "-3px" }} /> Draw the area to keep</span>}
      canUndo={history.canUndo}
      canRedo={history.canRedo}
      onUndo={history.undo}
      onRedo={history.redo}
      run={run}
      action={{ label: "Crop", disabled: full, hint: full ? "Shrink the box to trim the page." : null, onClick: () => void run.start("crop", args) }}
      sidebar={sidebar}
      canvas={{
        items: [item],
        selectedId: selected,
        onSelect: (id) => setSelected(id ?? "crop"),
        onBegin: history.checkpoint,
        onChange: (next) => next[0] && history.live(next[0].box),
        render: () => <div style={{ position: "absolute", inset: 0, boxShadow: "0 0 0 9999px rgba(10,20,30,.5)", outline: "1.5px solid #fff", pointerEvents: "none" }} />,
        mode: "rect",
        itemsFirst: true,
        onDraw: draw,
      }}
    />
  );
}

export default function CropEditor() {
  const state = useEditorDoc();
  return <DocGate state={state}>{(doc) => <CropBody key={doc.file} doc={doc} />}</DocGate>;
}
