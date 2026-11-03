import { useEffect, useRef, useState } from "preact/hooks";
import { MousePointer2 } from "lucide-preact";
import { DocGate, EditorShell } from "../canvas/EditorShell";
import { TextBlock } from "../canvas/ItemViews";
import { ToolButton } from "../canvas/ToolButton";
import { newId } from "../canvas/types";
import type { DocView, Gesture, RenderContext } from "../canvas/types";
import { useEditorDoc } from "../canvas/useEditorDoc";
import { useEditorRun } from "../canvas/useEditorRun";
import { useItemsEditor } from "../canvas/useItemsEditor";
import { imageSrc } from "../kit";
import { buildSignPlan, fieldItem, loadAssets, saveAssets, signatureItem } from "./assets";
import type { SigAsset, SignItem } from "./assets";
import { SignSidebar } from "./SignSidebar";

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function SignatureView({ asset }: { asset: SigAsset }) {
  if (asset.kind === "image") {
    return <img src={imageSrc(asset.path)} alt="Signature" draggable={false} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />;
  }
  return (
    <svg class="ed-svg" viewBox={`0 0 ${asset.w} ${asset.h}`} preserveAspectRatio="none">
      {asset.strokes.map((s) => (
        <path d={s.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ")} fill="none" stroke={asset.color} stroke-width={asset.width} stroke-linecap="round" stroke-linejoin="round" />
      ))}
    </svg>
  );
}

function SignBody({ doc }: { doc: DocView }) {
  const ed = useItemsEditor<SignItem>(doc.sizes);
  const run = useEditorRun("sign");
  const [assets, setAssets] = useState<SigAsset[]>(() => loadAssets());
  const [armedId, setArmedId] = useState<string | null>(null);
  const [armedField, setArmedField] = useState<"name" | "date" | null>(null);
  const [field, setField] = useState({ name: "", size: 14 });
  const [editingId, setEditingId] = useState<string | null>(null);
  const fresh = useRef<string | null>(null);
  const { history } = ed;

  useEffect(() => saveAssets(assets), [assets]);

  const armed = assets.find((a) => a.id === armedId) ?? null;
  const placing = armed !== null || armedField !== null;
  const disarm = () => { setArmedId(null); setArmedField(null); };

  const addAsset = (asset: SigAsset) => {
    setAssets((list) => [...list, asset]);
    setArmedId(asset.id);
    setArmedField(null);
  };

  const draw = (g: Gesture) => {
    const at = g.type === "click" ? g.pt : g.type === "rect" ? { x: g.box.x + g.box.w / 2, y: g.box.y + g.box.h / 2 } : g.points[0];
    const width = g.type === "rect" && g.box.w > 20 ? g.box.w : undefined;
    if (armed) {
      ed.add(signatureItem(newId(), g.page, armed, at, width));
      disarm();
    } else if (armedField) {
      const text = armedField === "date" ? today() : field.name.trim();
      const id = newId();
      ed.add(fieldItem(id, g.page, text, { x: at.x, y: at.y - field.size / 2 }, field.size));
      if (!text) { fresh.current = id; setEditingId(id); }
      disarm();
    }
  };

  const everyPage = () => {
    const s = ed.selected;
    if (!s || s.kind !== "signature") return;
    const copies = doc.sizes
      .map((_, p) => p)
      .filter((p) => p !== s.page)
      .map((p) => ({ ...s, id: newId(), page: p }));
    history.push([...history.get(), ...copies]);
  };

  const setText = (id: string, text: string) => history.live(history.get().map((i) => (i.id === id && i.kind === "field" ? { ...i, text } : i)));
  const editDone = (id: string) => {
    setEditingId(null);
    const item = history.get().find((i) => i.id === id);
    if (item?.kind === "field" && !item.text.trim()) {
      if (fresh.current === id) history.undo(); else ed.remove(id);
    }
    fresh.current = null;
  };

  const render = (item: SignItem, ctx: RenderContext) => {
    if (item.kind === "signature") return <SignatureView asset={item.asset} />;
    return (
      <TextBlock style={item} scale={ctx.scale} editing={editingId === item.id} onText={(t) => setText(item.id, t)} onFocus={history.checkpoint} onDone={() => editDone(item.id)} />
    );
  };

  const plan = buildSignPlan(doc.file, doc.password, ed.items);
  const count = (plan.args.items as unknown[]).length;
  const hint = count === 0 ? "Place a signature or text on the page first." : null;

  return (
    <EditorShell<SignItem>
      toolId="sign"
      doc={doc}
      page={ed.page}
      onPage={ed.setPage}
      counts={ed.counts}
      tools={
        <>
          <ToolButton icon={MousePointer2} label="Select" on={!placing} onClick={disarm} />
          {placing ? <span class="ed-zoom"><output style={{ minWidth: 0 }}>Click the page to place it</output></span> : null}
        </>
      }
      canUndo={history.canUndo}
      canRedo={history.canRedo}
      onUndo={history.undo}
      onRedo={history.redo}
      run={run}
      action={{ label: "Save signed copy", disabled: count === 0, hint, onClick: () => void run.start(plan.tool, plan.args) }}
      sidebar={
        <SignSidebar
          assets={assets}
          armedId={armedId}
          onAddAsset={addAsset}
          onDropAsset={(id) => { setAssets((l) => l.filter((a) => a.id !== id)); if (armedId === id) setArmedId(null); }}
          onArm={(id) => { setArmedId(id); setArmedField(null); ed.select(null); }}
          field={field}
          onField={(patch) => setField((f) => ({ ...f, ...patch }))}
          armedField={armedField}
          onArmField={(kind) => { setArmedField(armedField === kind ? null : kind); setArmedId(null); ed.select(null); }}
          selectionIsSignature={ed.selected?.kind === "signature"}
          onEveryPage={everyPage}
          onDelete={() => ed.selectedId && ed.remove(ed.selectedId)}
          hasSelection={!!ed.selected}
        />
      }
      canvas={{
        items: ed.items,
        selectedId: ed.selectedId,
        onSelect: ed.select,
        onBegin: history.checkpoint,
        onChange: history.live,
        render,
        mode: placing ? "rect" : "none",
        onDraw: draw,
        onItemDoubleClick: (id) => { if (history.get().find((i) => i.id === id)?.kind === "field") setEditingId(id); },
      }}
    />
  );
}

export default function SignEditor() {
  const state = useEditorDoc();
  return <DocGate state={state}>{(doc) => <SignBody key={doc.file} doc={doc} />}</DocGate>;
}
