import { Trash2 } from "lucide-preact";
import { ColorField, Group, NumberField, SelectField, Toggle } from "../../ui/fields";
import { CSS_FONTS } from "../canvas/ItemViews";
import type { EditStyle } from "./items";

const FONTS = Object.keys(CSS_FONTS).map((f) => ({ value: f, label: f }));

export type StyleKind = "text" | "shape" | "ink" | "whiteout" | "image" | "none";

const HELP: Record<StyleKind, string> = {
  none: "Pick a tool above, then click or drag on the page. Click an item to move it, resize it, or press Delete.",
  text: "Click the page to type. Double click text later to change it.",
  shape: "Drag on the page to draw. Drag the handles to adjust.",
  ink: "Draw freely with the mouse.",
  whiteout: "Drag over what you want to hide. It covers the area with a solid colour.",
  image: "Click the page to place the picture, or drag to choose its size.",
};

export function EditSidebar(props: {
  kind: StyleKind;
  style: EditStyle;
  onStyle: (patch: Partial<EditStyle>) => void;
  hasSelection: boolean;
  onDelete: () => void;
  count: number;
}) {
  const { kind, style: s, onStyle: set } = props;
  return (
    <>
      <p class="hint">{HELP[kind]}</p>
      {kind === "text" ? (
        <Group title="Text">
          <SelectField label="Font" value={s.font} options={FONTS} onChange={(font) => set({ font })} />
          <NumberField label="Size" value={s.size} min={6} max={200} unit="pt" onChange={(size) => set({ size })} />
          <ColorField label="Colour" value={s.color} onChange={(color) => set({ color })} />
          <div class="inline-toggles">
            <Toggle checked={s.bold} label="Bold" onChange={(bold) => set({ bold })} />
            <Toggle checked={s.italic} label="Italic" onChange={(italic) => set({ italic })} />
          </div>
        </Group>
      ) : null}
      {kind === "shape" ? (
        <Group title="Shape">
          <ColorField label="Outline" value={s.stroke} onChange={(stroke) => set({ stroke })} />
          <NumberField label="Line width" value={s.width} min={1} max={30} unit="pt" onChange={(width) => set({ width })} />
          <Toggle checked={s.fillOn} label="Fill inside" hint="Rectangles and ellipses" onChange={(fillOn) => set({ fillOn })} />
          {s.fillOn ? <ColorField label="Fill colour" value={s.fill} onChange={(fill) => set({ fill })} /> : null}
        </Group>
      ) : null}
      {kind === "ink" ? (
        <Group title="Pen">
          <ColorField label="Colour" value={s.color} onChange={(color) => set({ color })} />
          <NumberField label="Thickness" value={s.width} min={1} max={30} unit="pt" onChange={(width) => set({ width })} />
        </Group>
      ) : null}
      {kind === "whiteout" ? (
        <Group title="Cover">
          <ColorField label="Colour" value={s.whiteout} onChange={(whiteout) => set({ whiteout })} />
        </Group>
      ) : null}
      <Group title="Selected item">
        <button type="button" class="btn small" disabled={!props.hasSelection} onClick={props.onDelete}><Trash2 size={15} /> Delete item</button>
      </Group>
      <p class="hint">{props.count === 0 ? "Nothing added yet." : `${props.count} ${props.count === 1 ? "change" : "changes"} will be saved.`}</p>
    </>
  );
}
