import { useEffect, useState } from "preact/hooks";
import { engineCall } from "../engine/client";
import { Choices, Group, Hint, SelectField, TextField, Toggle } from "../ui/fields";
import { paths } from "./args";
import type { FormMap, FormProps } from "./types";

const officeForm = (noun: string) =>
  function OfficeForm({ value, set, ctx }: FormProps) {
    return (
      <Group title="Output">
        <Toggle
          checked={value.merge_output}
          label={`Join all ${noun} into one PDF`}
          hint={ctx.files.length > 1 ? "Otherwise each file becomes its own PDF" : undefined}
          onChange={(merge_output) => set({ merge_output })}
        />
        <Hint>Conversion uses the Microsoft Office apps installed on this computer, running out of sight.</Hint>
      </Group>
    );
  };

const office = (noun: string): FormMap[string] => ({
  defaults: { merge_output: false },
  Form: officeForm(noun),
  toArgs: (o, files) => ({ files: paths(files), merge_output: o.merge_output }),
});

const PAGE_SIZES = [
  { value: "fit", label: "Same as image" },
  { value: "a4", label: "A4" },
  { value: "letter", label: "Letter" },
] as const;

const images_to_pdf: FormMap[string] = {
  defaults: { orientation: "portrait", page_size: "fit", margin: "none", merge_output: true },
  Form: ({ value, set }) => (
    <>
      <Group title="Page">
        <Choices
          compact
          value={value.orientation}
          onChange={(orientation) => set({ orientation })}
          options={[{ value: "portrait", label: "Portrait" }, { value: "landscape", label: "Landscape" }]}
        />
        <SelectField label="Page size" value={value.page_size} options={PAGE_SIZES} onChange={(page_size) => set({ page_size })} />
        <SelectField
          label="Margin"
          value={value.margin}
          options={[{ value: "none", label: "None" }, { value: "small", label: "Small" }, { value: "big", label: "Big" }]}
          onChange={(margin) => set({ margin })}
        />
      </Group>
      <Group>
        <Toggle checked={value.merge_output} label="Put all images in one PDF" hint="Otherwise one PDF per image" onChange={(merge_output) => set({ merge_output })} />
      </Group>
    </>
  ),
  toArgs: (o, files) => ({ files: paths(files), ...o }),
};

const html_to_pdf: FormMap[string] = {
  defaults: { source: "", page_size: "a4", orientation: "portrait", margin: "small", one_long_page: false },
  Form: ({ value, set, ctx }) => (
    <>
      <Group title="Page to save">
        <TextField
          label="Web address or file"
          value={value.source || ctx.files[0]?.path || ""}
          placeholder="https://example.com"
          dir="ltr"
          onInput={(source) => set({ source })}
          hint="The page is fetched with this computer's internet connection."
        />
      </Group>
      <Group title="Page">
        <Choices
          compact
          value={value.orientation}
          onChange={(orientation) => set({ orientation })}
          options={[{ value: "portrait", label: "Portrait" }, { value: "landscape", label: "Landscape" }]}
        />
        <SelectField label="Page size" value={value.page_size} options={PAGE_SIZES.filter((s) => s.value !== "fit")} onChange={(page_size) => set({ page_size })} />
        <SelectField
          label="Margin"
          value={value.margin}
          options={[{ value: "none", label: "None" }, { value: "small", label: "Small" }, { value: "big", label: "Big" }]}
          onChange={(margin) => set({ margin })}
        />
        <Toggle checked={value.one_long_page} label="One long page" hint="No page breaks" onChange={(one_long_page) => set({ one_long_page })} />
      </Group>
    </>
  ),
  toArgs: (o, files) => ({ ...o, source: (o.source || files[0]?.path || "").trim() }),
  check: (o, files) => ((o.source || files[0]?.path || "").trim() ? null : "Type a web address or choose an HTML file."),
};

interface Scanner {
  value: string;
  label: string;
}

function readScanners(summary: Record<string, unknown>): Scanner[] {
  const raw = (summary.devices ?? summary.scanners ?? []) as unknown[];
  return raw.map((item) => {
    if (typeof item === "string") return { value: item, label: item };
    const entry = item as { id?: string; name?: string };
    return { value: entry.id ?? entry.name ?? "", label: entry.name ?? entry.id ?? "Scanner" };
  });
}

function ScanForm({ value, set }: FormProps) {
  const [scanners, setScanners] = useState<Scanner[] | null>(null);
  useEffect(() => {
    let alive = true;
    engineCall("list_scanners")
      .then((r) => alive && setScanners(readScanners(r.summary)))
      .catch(() => alive && setScanners([]));
    return () => { alive = false; };
  }, []);

  return (
    <>
      <Group title="Scanner">
        {scanners === null ? <Hint>Looking for scanners.</Hint> : null}
        {scanners?.length === 0 ? <Hint>No scanner found. Connect one, switch it on, then reopen this tool.</Hint> : null}
        {scanners?.length ? (
          <SelectField label="Device" value={value.device || scanners[0].value} options={scanners} onChange={(device) => set({ device })} />
        ) : null}
      </Group>
      <Group title="Quality">
        <Choices
          compact
          value={value.dpi}
          onChange={(dpi) => set({ dpi })}
          options={[{ value: 150, label: "150" }, { value: 200, label: "200" }, { value: 300, label: "300" }, { value: 600, label: "600" }]}
        />
        <Hint>Dots per inch. 200 reads well and stays small; 300 is better for text recognition.</Hint>
        <Toggle checked={value.color} label="Scan in colour" onChange={(color) => set({ color })} />
      </Group>
    </>
  );
}

const scan_to_pdf: FormMap[string] = {
  defaults: { device: "", dpi: 200, color: true },
  Form: ScanForm,
  toArgs: (o) => ({ dpi: o.dpi, color: o.color, ...(o.device ? { device: o.device } : {}) }),
};

export const specs: FormMap = {
  word_to_pdf: office("documents"),
  ppt_to_pdf: office("presentations"),
  excel_to_pdf: office("spreadsheets"),
  images_to_pdf,
  html_to_pdf,
  scan_to_pdf,
};
