import { useState } from "preact/hooks";
import { ImagePlus } from "lucide-preact";
import { fileName, pickFiles } from "../engine/files";
import { Choices, ColorField, Group, NumberField, SelectField, Slider, TextField, Toggle } from "../ui/fields";
import { fileArgs } from "./args";
import type { FormMap } from "./types";

const FONTS = ["Arial", "Times", "Courier", "Segoe UI", "Tahoma", "Verdana", "Calibri"].map((f) => ({ value: f, label: f }));

const GRID_NINE = [
  "top-left", "top-center", "top-right",
  "middle-left", "center", "middle-right",
  "bottom-left", "bottom-center", "bottom-right",
] as const;

const GRID_SIX = ["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"] as const;

function PositionGrid(props: { cells: readonly string[]; value: string; onChange: (cell: string) => void }) {
  return (
    <div class="pos-grid" role="radiogroup" aria-label="Position">
      {props.cells.map((cell) => (
        <button
          type="button"
          role="radio"
          aria-checked={cell === props.value}
          aria-label={cell.replace("-", " ")}
          class={cell === props.value ? "pos on" : "pos"}
          onClick={() => props.onChange(cell)}
        />
      ))}
    </div>
  );
}

function PageWindow(props: { from: number; to: number; onChange: (patch: { from_page: number; to_page: number }) => void }) {
  return (
    <div class="two-col">
      <NumberField label="From page" value={props.from} min={1} onChange={(from_page) => props.onChange({ from_page, to_page: props.to })} />
      <NumberField label="To page" value={props.to} min={0} onChange={(to_page) => props.onChange({ from_page: props.from, to_page })} />
    </div>
  );
}

const watermark: FormMap[string] = {
  defaults: {
    kind: "text", text: "CONFIDENTIAL", font: "Arial", size: 48, bold: true, italic: false, underline: false,
    color: "#64748b", image_path: "", position: "center", mosaic: false, opacity: 40, rotation: 45,
    layer: "over", from_page: 1, to_page: 0,
  },
  Form: function WatermarkForm({ value, set }) {
    const [busy, setBusy] = useState(false);
    const choose = async () => {
      setBusy(true);
      const [picked] = await pickFiles({ accepts: ["png", "jpg", "jpeg"], multiple: false, title: "Choose a picture" });
      setBusy(false);
      if (picked) set({ image_path: picked });
    };
    return (
      <>
        <Group title="Mark">
          <Choices compact value={value.kind} onChange={(kind) => set({ kind })} options={[{ value: "text", label: "Text" }, { value: "image", label: "Picture" }]} />
          {value.kind === "text" ? (
            <>
              <TextField label="Text" value={value.text} onInput={(text) => set({ text })} />
              <SelectField label="Font" value={value.font} options={FONTS} onChange={(font) => set({ font })} />
              <NumberField label="Size" value={value.size} min={6} max={300} unit="pt" onChange={(size) => set({ size })} />
              <ColorField label="Colour" value={value.color} onChange={(color) => set({ color })} />
              <div class="inline-toggles">
                <Toggle checked={value.bold} label="Bold" onChange={(bold) => set({ bold })} />
                <Toggle checked={value.italic} label="Italic" onChange={(italic) => set({ italic })} />
                <Toggle checked={value.underline} label="Underline" onChange={(underline) => set({ underline })} />
              </div>
            </>
          ) : (
            <div class="pick-row">
              <button type="button" class="btn small" disabled={busy} onClick={() => void choose()}>
                <ImagePlus size={16} /> Choose picture
              </button>
              <span class="pick-name" dir="ltr">{value.image_path ? fileName(value.image_path) : "No picture chosen"}</span>
            </div>
          )}
        </Group>
        <Group title="Placement">
          <PositionGrid cells={GRID_NINE} value={value.position} onChange={(position) => set({ position })} />
          <Toggle checked={value.mosaic} label="Repeat across the page" onChange={(mosaic) => set({ mosaic })} />
          <Slider label="Opacity" value={value.opacity} min={5} max={100} step={5} format={(v) => `${v}%`} onChange={(opacity) => set({ opacity })} />
          <Slider label="Rotation" value={value.rotation} min={0} max={359} step={15} format={(v) => `${v} degrees`} onChange={(rotation) => set({ rotation })} />
          <Choices compact value={value.layer} onChange={(layer) => set({ layer })} options={[{ value: "over", label: "Over the text" }, { value: "under", label: "Behind the text" }]} />
        </Group>
        <Group title="Pages">
          <PageWindow from={value.from_page} to={value.to_page} onChange={set} />
          <small class="field-hint">Set "To page" to 0 to go to the last page.</small>
        </Group>
      </>
    );
  },
  toArgs: (o, files) => {
    const args: Record<string, unknown> = {
      ...fileArgs(files), kind: o.kind, position: o.position, mosaic: o.mosaic,
      opacity: o.opacity / 100, rotation: o.rotation, layer: o.layer, from_page: o.from_page,
    };
    if (o.to_page > 0) args.to_page = o.to_page;
    if (o.kind === "text") {
      Object.assign(args, { text: o.text, font: o.font, size: o.size, bold: o.bold, italic: o.italic, underline: o.underline, color: o.color });
    } else {
      args.image_path = o.image_path;
    }
    return args;
  },
  check: (o) => {
    if (o.kind === "text" && !o.text.trim()) return "Type the text for the watermark.";
    if (o.kind === "image" && !o.image_path) return "Choose a picture for the watermark.";
    return null;
  },
};

const page_numbers: FormMap[string] = {
  defaults: {
    position: "bottom-center", margin: "recommended", first_number: 1, from_page: 1, to_page: 0,
    format: "{n}", facing: false, font: "Arial", size: 12, bold: false, italic: false, color: "#000000", arabic: false,
  },
  Form: ({ value, set }) => (
    <>
      <Group title="Position">
        <PositionGrid cells={GRID_SIX} value={value.position} onChange={(position) => set({ position })} />
        <SelectField
          label="Distance from the edge"
          value={value.margin}
          options={[{ value: "small", label: "Small" }, { value: "recommended", label: "Recommended" }, { value: "big", label: "Big" }]}
          onChange={(margin) => set({ margin })}
        />
        <Toggle checked={value.facing} label="Facing pages" hint="Mirror left and right on even pages" onChange={(facing) => set({ facing })} />
      </Group>
      <Group title="Text">
        <Choices
          value={value.format}
          onChange={(format) => set({ format })}
          options={[
            { value: "{n}", label: "7" },
            { value: "Page {n}", label: "Page 7" },
            { value: "Page {n} of {total}", label: "Page 7 of 20" },
          ]}
        />
        <Toggle checked={value.arabic} label="Arabic digits" hint="Shows 7 as ٧" onChange={(arabic) => set({ arabic })} />
        <SelectField label="Font" value={value.font} options={FONTS} onChange={(font) => set({ font })} />
        <NumberField label="Size" value={value.size} min={6} max={72} unit="pt" onChange={(size) => set({ size })} />
        <ColorField label="Colour" value={value.color} onChange={(color) => set({ color })} />
        <div class="inline-toggles">
          <Toggle checked={value.bold} label="Bold" onChange={(bold) => set({ bold })} />
          <Toggle checked={value.italic} label="Italic" onChange={(italic) => set({ italic })} />
        </div>
      </Group>
      <Group title="Pages">
        <NumberField label="First number" value={value.first_number} min={0} onChange={(first_number) => set({ first_number })} />
        <PageWindow from={value.from_page} to={value.to_page} onChange={set} />
        <small class="field-hint">Set "To page" to 0 to go to the last page.</small>
      </Group>
    </>
  ),
  toArgs: (o, files) => {
    const { arabic, to_page, ...rest } = o;
    return { ...fileArgs(files), ...rest, ...(to_page > 0 ? { to_page } : {}), numerals: arabic ? "arabic" : "latin" };
  },
};

export const specs: FormMap = { watermark, page_numbers };
