import { Choices, Group, Hint, SelectField, TextField, PasswordField, Toggle } from "../ui/fields";
import { fileArgs, pageListProblem, parsePageList } from "./args";
import type { FormMap } from "./types";

// Only the language packs shipped in the app's argos folder; others fail with "not available offline".
const LANGS = [
  { value: "en", label: "English" },
  { value: "ar", label: "Arabic" },
] as const;

const translate: FormMap[string] = {
  defaults: { source: "en", target: "ar" },
  Form: ({ value, set }) => (
    <>
      <Group title="Languages">
        <SelectField label="From" value={value.source} options={LANGS} onChange={(source) => set({ source })} />
        <SelectField label="To" value={value.target} options={LANGS} onChange={(target) => set({ target })} />
      </Group>
      <Hint>Translation runs on this computer. The first run of a language pair can take a little longer.</Hint>
    </>
  ),
  toArgs: (o, files) => ({ ...fileArgs(files), source: o.source, target: o.target }),
  check: (o) => (o.source === o.target ? "Pick two different languages." : null),
};

const summarize: FormMap[string] = {
  defaults: { length: "medium", pages: "" },
  Form: ({ value, set }) => (
    <>
      <Group title="Length">
        <Choices
          value={value.length}
          onChange={(length) => set({ length })}
          options={[
            { value: "short", label: "Short", hint: "A few key sentences" },
            { value: "medium", label: "Medium", hint: "A paragraph or two" },
            { value: "long", label: "Long", hint: "More detail" },
          ]}
        />
      </Group>
      <Group title="Pages">
        <TextField label="Pages" value={value.pages} placeholder="All pages" dir="ltr" onInput={(pages) => set({ pages })} hint="Leave empty for the whole file, or type 1-3, 7." />
      </Group>
    </>
  ),
  toArgs: (o, files) => {
    const pages = parsePageList(o.pages);
    return { ...fileArgs(files), length: o.length, ...(pages ? { pages } : {}) };
  },
  check: (o) => pageListProblem(o.pages),
};

const protect: FormMap[string] = {
  defaults: { new_password: "", repeat: "", allow_print: true, allow_copy: true, allow_modify: false },
  Form: ({ value, set }) => (
    <>
      <Group title="Password">
        <PasswordField label="Password" value={value.new_password} onInput={(new_password) => set({ new_password })} />
        <PasswordField label="Type it again" value={value.repeat} onInput={(repeat) => set({ repeat })} />
        <Hint>There is no way to recover a forgotten password, so keep it somewhere safe.</Hint>
      </Group>
      <Group title="People who open it can">
        <Toggle checked={value.allow_print} label="Print" onChange={(allow_print) => set({ allow_print })} />
        <Toggle checked={value.allow_copy} label="Copy text" onChange={(allow_copy) => set({ allow_copy })} />
        <Toggle checked={value.allow_modify} label="Edit" onChange={(allow_modify) => set({ allow_modify })} />
      </Group>
    </>
  ),
  // Here `password` is the NEW password; the one that opens a locked file is `current_password`.
  toArgs: (o, files) => {
    const { password: opening, ...rest } = fileArgs(files);
    return {
      ...rest,
      ...(opening ? { current_password: opening } : {}),
      password: o.new_password,
      allow_print: o.allow_print,
      allow_copy: o.allow_copy,
      allow_modify: o.allow_modify,
    };
  },
  check: (o) => {
    if (!o.new_password) return "Choose a password.";
    return o.new_password === o.repeat ? null : "The two passwords are not the same.";
  },
};

const unlock: FormMap[string] = {
  defaults: {},
  Form: () => <Hint>If the file asks for a password, enter it when prompted. The unlocked copy is saved next to the original.</Hint>,
  toArgs: (_o, files) => fileArgs(files),
};

export const specs: FormMap = { translate, summarize, protect, unlock };
