import { Choices, Group, Hint, LanguageChips, NumberField, OCR_LANGUAGES, Slider, TextField, Toggle } from "../ui/fields";
import { fileArgs, pageListProblem, parsePageList } from "./args";
import type { JSX } from "preact";
import type { FormMap, FormProps, Opts } from "./types";

function OcrBlock({ value, set }: FormProps) {
  return (
    <Group title="Scanned pages">
      <Toggle checked={value.ocr} label="Recognize text first" hint="Turn on for scans and photos of pages" onChange={(ocr) => set({ ocr })} />
      {value.ocr ? <LanguageChips value={value.languages} options={OCR_LANGUAGES} onChange={(languages) => set({ languages })} /> : null}
    </Group>
  );
}

const withOcr = (extra: Opts = {}, ExtraForm?: (p: FormProps) => JSX.Element | null): FormMap[string] => ({
  defaults: { ocr: false, languages: ["eng", "ara"], ...extra },
  Form: (props) => (
    <>
      <OcrBlock {...props} />
      {ExtraForm ? <ExtraForm {...props} /> : null}
    </>
  ),
  toArgs: (o, files) => ({
    ...fileArgs(files),
    ocr: o.ocr,
    languages: o.languages,
    ...(o.one_sheet !== undefined ? { one_sheet: o.one_sheet } : {}),
  }),
});

const pdf_to_excel = withOcr({ one_sheet: false }, ({ value, set }) => (
  <Group title="Sheets">
    <Toggle checked={value.one_sheet} label="Put everything on one sheet" hint="Otherwise each table gets its own sheet" onChange={(one_sheet) => set({ one_sheet })} />
  </Group>
));

const pdf_to_images: FormMap[string] = {
  defaults: { mode: "pages", format: "jpg", dpi: 150, quality: 85, pages: "", zip: true },
  Form: ({ value, set }) => (
    <>
      <Group title="What to save">
        <Choices
          value={value.mode}
          onChange={(mode) => set({ mode })}
          options={[
            { value: "pages", label: "Whole pages", hint: "One picture per page" },
            { value: "extract", label: "Pictures inside", hint: "Only the images placed in the file" },
          ]}
        />
      </Group>
      <Group title="Picture">
        <Choices
          compact
          value={value.format}
          onChange={(format) => set({ format })}
          options={[{ value: "jpg", label: "JPG" }, { value: "png", label: "PNG" }]}
        />
        {value.mode === "pages" ? (
          <NumberField label="Detail" value={value.dpi} min={72} max={600} step={25} unit="dpi" onChange={(dpi) => set({ dpi })} />
        ) : null}
        {value.format === "jpg" ? <Slider label="Quality" value={value.quality} min={30} max={100} format={(v) => `${v}%`} onChange={(quality) => set({ quality })} /> : null}
      </Group>
      <Group title="Pages">
        <TextField label="Pages" value={value.pages} placeholder="All pages" dir="ltr" onInput={(pages) => set({ pages })} hint="Leave empty for all, or type 1-3, 7." />
        <Toggle checked={value.zip} label="Put pictures in one ZIP" onChange={(zip) => set({ zip })} />
      </Group>
    </>
  ),
  toArgs: (o, files) => {
    const pages = parsePageList(o.pages);
    const args: Record<string, unknown> = { ...fileArgs(files), mode: o.mode, format: o.format, quality: o.quality, zip: o.zip };
    if (o.mode === "pages") args.dpi = o.dpi;
    if (pages) args.pages = pages;
    return args;
  },
  check: (o) => pageListProblem(o.pages),
};

const pdf_to_text: FormMap[string] = {
  defaults: { pages: "" },
  Form: ({ value, set }) => (
    <Group title="Pages">
      <TextField label="Pages" value={value.pages} placeholder="All pages" dir="ltr" onInput={(pages) => set({ pages })} hint="Leave empty for the whole file, or type 1-3, 7." />
      <Hint>If a page is a scan with no real text, run Recognize text first.</Hint>
    </Group>
  ),
  toArgs: (o, files) => {
    const pages = parsePageList(o.pages);
    return { ...fileArgs(files), ...(pages ? { pages } : {}) };
  },
  check: (o) => pageListProblem(o.pages),
};

export const specs: FormMap = {
  pdf_to_word: withOcr(),
  pdf_to_ppt: withOcr(),
  pdf_to_excel,
  pdf_to_images,
  pdf_to_text,
};
