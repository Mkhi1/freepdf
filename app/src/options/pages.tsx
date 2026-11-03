import { ArrowDownAZ, ArrowUpDown } from "lucide-preact";
import { Choices, Group, Hint, NumberField, TextField, Toggle } from "../ui/fields";
import { fileArgs, pageListProblem, parsePageList } from "./args";
import type { FormMap } from "./types";

const merge: FormMap[string] = {
  defaults: {},
  Form: ({ ctx }) => (
    <>
      <Group title="Order">
        <Hint>Files are joined in the order shown. Use the arrows on each file to move it.</Hint>
        <div class="btn-row">
          <button type="button" class="btn small" onClick={() => ctx.reorder([...ctx.files].sort((a, b) => a.name.localeCompare(b.name)))}>
            <ArrowDownAZ size={16} /> Sort by name
          </button>
          <button type="button" class="btn small" onClick={() => ctx.reorder([...ctx.files].reverse())}>
            <ArrowUpDown size={16} /> Reverse
          </button>
        </div>
      </Group>
      <Hint>Password-protected files will ask for their password before you can continue.</Hint>
    </>
  ),
  toArgs: (_o, files) => ({
    files: files.map((f) => ({ path: f.path, ...(f.password ? { password: f.password } : {}) })),
  }),
  check: (_o, files) => (files.length < 2 ? "Add at least two files to merge." : null),
};

const split: FormMap[string] = {
  defaults: { mode: "ranges", ranges: "", every: 2, max_mb: 5, merge_output: false, zip: true },
  Form: ({ value, set }) => (
    <>
      <Group title="How to split">
        <Choices
          value={value.mode}
          onChange={(mode) => set({ mode })}
          options={[
            { value: "ranges", label: "Custom ranges", hint: "Each range becomes its own file" },
            { value: "every", label: "Fixed length", hint: "A new file every few pages" },
            { value: "extract_all", label: "Every page", hint: "One file per page" },
            { value: "extract", label: "Pick pages", hint: "Keep only the pages you list" },
            { value: "size", label: "By file size", hint: "Parts no bigger than a limit" },
          ]}
        />
      </Group>
      {value.mode === "ranges" || value.mode === "extract" ? (
        <Group>
          <TextField label="Pages" value={value.ranges} placeholder="1-3, 4-9, 10" onInput={(ranges) => set({ ranges })} dir="ltr" hint="Numbers start at 1. Separate ranges with commas." />
          {value.mode === "ranges" ? <Toggle checked={value.merge_output} label="Join all ranges into one file" onChange={(merge_output) => set({ merge_output })} /> : null}
        </Group>
      ) : null}
      {value.mode === "every" ? (
        <Group>
          <NumberField label="Pages in each file" value={value.every} min={1} onChange={(every) => set({ every })} />
        </Group>
      ) : null}
      {value.mode === "size" ? (
        <Group>
          <NumberField label="Largest part" value={value.max_mb} min={0.1} step={0.5} unit="MB" onChange={(max_mb) => set({ max_mb })} />
        </Group>
      ) : null}
      <Group>
        <Toggle checked={value.zip} label="Put several files in one ZIP" hint="Easier to move around" onChange={(zip) => set({ zip })} />
      </Group>
    </>
  ),
  toArgs: (o, files) => {
    const args: Record<string, unknown> = { ...fileArgs(files), mode: o.mode, zip: o.zip };
    if (o.mode === "ranges" || o.mode === "extract") args.ranges = o.ranges.trim();
    if (o.mode === "ranges") args.merge_output = o.merge_output;
    if (o.mode === "every") args.every = Math.max(1, Math.round(o.every));
    if (o.mode === "size") args.max_mb = o.max_mb;
    return args;
  },
  check: (o) => {
    if ((o.mode === "ranges" || o.mode === "extract") && !o.ranges.trim()) return "Type the pages you want, for example 1-3, 7.";
    if (o.mode === "ranges" || o.mode === "extract") return pageListProblem(o.ranges);
    return null;
  },
};

const rotate: FormMap[string] = {
  defaults: { angle: 90, pages: "" },
  Form: ({ value, set }) => (
    <>
      <Group title="Turn pages">
        <Choices
          value={value.angle}
          onChange={(angle) => set({ angle })}
          options={[
            { value: 90, label: "Right", hint: "90 degrees clockwise" },
            { value: 180, label: "Upside down", hint: "180 degrees" },
            { value: 270, label: "Left", hint: "90 degrees anticlockwise" },
          ]}
        />
      </Group>
      <Group title="Which pages">
        <TextField label="Pages" value={value.pages} placeholder="All pages" onInput={(pages) => set({ pages })} dir="ltr" hint="Leave empty to turn every page, or type 1-3, 7." />
      </Group>
    </>
  ),
  toArgs: (o, files) => {
    const pages = parsePageList(o.pages);
    return { ...fileArgs(files), angle: o.angle, ...(pages ? { pages } : {}) };
  },
  check: (o) => pageListProblem(o.pages),
};

export const specs: FormMap = { merge, split, rotate };
