import { useState } from "preact/hooks";
import { CalendarDays, ImagePlus, Loader, Trash2, UserRound } from "lucide-preact";
import { engineCall, fileName, imageSrc, pickFiles } from "../kit";
import { Choices, ColorField, Group, NumberField, SelectField, TextField } from "../../ui/fields";
import type { Pt } from "../canvas/geometry";
import { newId } from "../canvas/types";
import { drawnAsset, imageAspect } from "./assets";
import type { SigAsset } from "./assets";
import { SignaturePad } from "./SignaturePad";

type Tab = "draw" | "type" | "upload";

const STYLES = [
  { value: "script", label: "Script" }, { value: "print", label: "Handwritten" }, { value: "ink", label: "Ink" },
  { value: "brush", label: "Brush" }, { value: "formal", label: "Formal" }, { value: "bold", label: "Bold" }, { value: "gabriola", label: "Flowing" },
];

export interface SignSidebarProps {
  assets: readonly SigAsset[];
  armedId: string | null;
  onAddAsset: (asset: SigAsset) => void;
  onDropAsset: (id: string) => void;
  onArm: (id: string | null) => void;
  field: { name: string; size: number };
  onField: (patch: Partial<{ name: string; size: number }>) => void;
  onArmField: (kind: "name" | "date") => void;
  armedField: "name" | "date" | null;
  selectionIsSignature: boolean;
  onEveryPage: () => void;
  onDelete: () => void;
  hasSelection: boolean;
}

function AssetThumb({ asset }: { asset: SigAsset }) {
  if (asset.kind === "image") return <img class="ed-sig" src={imageSrc(asset.path)} alt="" />;
  return (
    <svg class="ed-sig" viewBox={`0 0 ${asset.w} ${asset.h}`} style={{ width: "100%", height: "44px" }}>
      {asset.strokes.map((s) => (
        <path d={s.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ")} fill="none" stroke={asset.color} stroke-width={asset.width} stroke-linecap="round" stroke-linejoin="round" />
      ))}
    </svg>
  );
}

function TypeTab(props: { onAdd: (a: SigAsset) => void }) {
  const [text, setText] = useState("");
  const [font, setFont] = useState("script");
  const [color, setColor] = useState("#0d1a73");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const make = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await engineCall("make_signature", { text, font, color });
      const path = String(r.summary.path);
      props.onAdd({ id: newId("s"), kind: "image", label: text, path, aspect: await imageAspect(path) });
      setText("");
    } catch (e) {
      setError((e as { message?: string }).message ?? "The signature could not be made.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <TextField label="Your name" value={text} onInput={setText} placeholder="Type your name" />
      <SelectField label="Style" value={font} options={STYLES} onChange={setFont} />
      <ColorField label="Colour" value={color} onChange={setColor} />
      {error ? <p class="ed-warn" role="alert">{error}</p> : null}
      <button type="button" class="btn small" disabled={!text.trim() || busy} onClick={() => void make()}>
        {busy ? <Loader size={14} class="spin" /> : null} Make signature
      </button>
    </>
  );
}

function DrawTab(props: { onAdd: (a: SigAsset) => void }) {
  const [strokes, setStrokes] = useState<Pt[][]>([]);
  const [color, setColor] = useState("#0d1a73");
  const use = () => {
    const asset = drawnAsset(newId("s"), strokes, color);
    if (asset) { props.onAdd(asset); setStrokes([]); }
  };
  return (
    <>
      <SignaturePad color={color} onColor={setColor} strokes={strokes} onStrokes={setStrokes} />
      <button type="button" class="btn small" disabled={!strokes.length} onClick={use}>Save signature</button>
    </>
  );
}

function UploadTab(props: { onAdd: (a: SigAsset) => void }) {
  const choose = async () => {
    const [path] = await pickFiles({ accepts: ["png", "jpg", "jpeg"], multiple: false, title: "Choose a signature picture" });
    if (path) props.onAdd({ id: newId("s"), kind: "image", label: fileName(path), path, aspect: await imageAspect(path) });
  };
  return (
    <>
      <p class="hint">Use a picture of your signature. A PNG with a clear background looks best.</p>
      <button type="button" class="btn small" onClick={() => void choose()}><ImagePlus size={15} /> Choose picture</button>
    </>
  );
}

export function SignSidebar(p: SignSidebarProps) {
  const [tab, setTab] = useState<Tab>("draw");
  return (
    <>
      <Group title="Make a signature">
        <Choices compact value={tab} onChange={setTab} options={[{ value: "draw", label: "Draw" }, { value: "type", label: "Type" }, { value: "upload", label: "Upload" }]} />
        {tab === "draw" ? <DrawTab onAdd={p.onAddAsset} /> : null}
        {tab === "type" ? <TypeTab onAdd={p.onAddAsset} /> : null}
        {tab === "upload" ? <UploadTab onAdd={p.onAddAsset} /> : null}
      </Group>
      <Group title="Your signatures">
        {p.assets.length === 0 ? <p class="hint">Make one above, then click it to place it on the page.</p> : null}
        <ul class="ed-list">
          {p.assets.map((a) => (
            <li key={a.id} style={a.id === p.armedId ? { borderColor: "var(--accent)", background: "var(--accent-soft)" } : undefined}>
              <button type="button" class="ed-sigbtn" style={{ flex: 1, minWidth: 0, background: "transparent", border: 0, padding: 0 }}
                aria-label="Place this signature" onClick={() => p.onArm(a.id === p.armedId ? null : a.id)}>
                <AssetThumb asset={a} />
              </button>
              <button type="button" class="icon-btn" aria-label="Remove from list" onClick={() => p.onDropAsset(a.id)}><Trash2 size={15} /></button>
            </li>
          ))}
        </ul>
        {p.armedId ? <p class="hint">Click the page to place it, or drag to set its size.</p> : null}
      </Group>
      <Group title="Text fields">
        <TextField label="Name" value={p.field.name} onInput={(name) => p.onField({ name })} placeholder="Your full name" />
        <NumberField label="Text size" value={p.field.size} min={6} max={60} unit="pt" onChange={(size) => p.onField({ size })} />
        <div class="btn-row">
          <button type="button" class={p.armedField === "name" ? "btn small primary" : "btn small"} onClick={() => p.onArmField("name")}><UserRound size={15} /> Place name</button>
          <button type="button" class={p.armedField === "date" ? "btn small primary" : "btn small"} onClick={() => p.onArmField("date")}><CalendarDays size={15} /> Place date</button>
        </div>
      </Group>
      <Group title="Selected item">
        <div class="btn-row">
          <button type="button" class="btn small" disabled={!p.selectionIsSignature} onClick={p.onEveryPage}>Copy to every page</button>
          <button type="button" class="btn small" disabled={!p.hasSelection} onClick={p.onDelete}><Trash2 size={15} /> Delete</button>
        </div>
      </Group>
    </>
  );
}
