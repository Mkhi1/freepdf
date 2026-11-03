import { Choices, Group, Hint, LanguageChips, OCR_LANGUAGES, TextField } from "../ui/fields";
import { fileArgs, pageListProblem, parsePageList } from "./args";
import type { FormMap } from "./types";

const compress: FormMap[string] = {
  defaults: { level: "recommended" },
  Form: ({ value, set }) => (
    <Group title="How small?">
      <Choices
        value={value.level}
        onChange={(level) => set({ level })}
        options={[
          { value: "extreme", label: "Smallest file", hint: "Lower picture quality" },
          { value: "recommended", label: "Balanced", hint: "Good quality, much smaller" },
          { value: "less", label: "Best quality", hint: "Only a little smaller" },
        ]}
      />
    </Group>
  ),
  toArgs: (o, files) => ({ ...fileArgs(files), level: o.level }),
};

const repair: FormMap[string] = {
  defaults: {},
  Form: () => <Hint>Free PDF rebuilds the file structure and keeps every page it can read. Your original stays untouched.</Hint>,
  toArgs: (_o, files) => fileArgs(files),
};

const pdfa: FormMap[string] = {
  defaults: { conformance: "2b" },
  Form: ({ value, set }) => (
    <Group title="Archive level">
      <Choices
        value={value.conformance}
        onChange={(conformance) => set({ conformance })}
        options={[
          { value: "1b", label: "PDF/A-1b", hint: "Oldest, most widely accepted" },
          { value: "2b", label: "PDF/A-2b", hint: "Recommended for most uses" },
          { value: "3b", label: "PDF/A-3b", hint: "Allows attached files" },
        ]}
      />
    </Group>
  ),
  toArgs: (o, files) => ({ ...fileArgs(files), conformance: o.conformance }),
};

const ocr: FormMap[string] = {
  defaults: { languages: ["eng", "ara"], pages: "" },
  Form: ({ value, set }) => (
    <>
      <Group title="Languages on the pages">
        <LanguageChips value={value.languages} options={OCR_LANGUAGES} onChange={(languages) => set({ languages })} />
        <Hint>Pick every language that appears. More languages can be a little slower.</Hint>
      </Group>
      <Group title="Which pages">
        <TextField label="Pages" value={value.pages} placeholder="All pages" onInput={(pages) => set({ pages })} dir="ltr" hint="Leave empty for the whole file, or type 1-3, 7." />
      </Group>
    </>
  ),
  toArgs: (o, files) => {
    const pages = parsePageList(o.pages);
    return { ...fileArgs(files), languages: o.languages, ...(pages ? { pages } : {}) };
  },
  check: (o) => pageListProblem(o.pages),
};

export const specs: FormMap = { compress, repair, pdfa, ocr };
