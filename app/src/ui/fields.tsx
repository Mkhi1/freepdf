import type { ComponentChildren } from "preact";

export function Group({ title, children }: { title?: string; children: ComponentChildren }) {
  return (
    <section class="group">
      {title ? <h3 class="group-title">{title}</h3> : null}
      {children}
    </section>
  );
}

export function Hint({ children }: { children: ComponentChildren }) {
  return <p class="hint">{children}</p>;
}

export interface Choice<T extends string | number> {
  value: T;
  label: string;
  hint?: string;
}

export function Choices<T extends string | number>(props: {
  value: T;
  options: readonly Choice<T>[];
  onChange: (value: T) => void;
  compact?: boolean;
}) {
  return (
    <div class={props.compact ? "choices compact" : "choices"} role="radiogroup">
      {props.options.map((option) => (
        <button
          type="button"
          role="radio"
          aria-checked={option.value === props.value}
          class={option.value === props.value ? "choice on" : "choice"}
          onClick={() => props.onChange(option.value)}
        >
          <span class="choice-label">{option.label}</span>
          {option.hint ? <span class="choice-hint">{option.hint}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Toggle(props: { checked: boolean; label: string; hint?: string; onChange: (on: boolean) => void }) {
  return (
    <label class="toggle">
      <input type="checkbox" checked={props.checked} onChange={(e) => props.onChange(e.currentTarget.checked)} />
      <span class="toggle-box" aria-hidden="true" />
      <span class="toggle-text">
        {props.label}
        {props.hint ? <small>{props.hint}</small> : null}
      </span>
    </label>
  );
}

export function TextField(props: {
  label: string;
  value: string;
  onInput: (value: string) => void;
  placeholder?: string;
  type?: "text" | "password";
  hint?: string;
  dir?: "ltr" | "rtl" | "auto";
}) {
  return (
    <label class="field">
      <span class="field-label">{props.label}</span>
      <input
        class="input"
        type={props.type ?? "text"}
        value={props.value}
        placeholder={props.placeholder}
        dir={props.dir ?? "auto"}
        onInput={(e) => props.onInput(e.currentTarget.value)}
      />
      {props.hint ? <small class="field-hint">{props.hint}</small> : null}
    </label>
  );
}

export function NumberField(props: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label class="field">
      <span class="field-label">{props.label}</span>
      <span class="input-unit">
        <input
          class="input"
          type="number"
          value={props.value}
          min={props.min}
          max={props.max}
          step={props.step}
          onInput={(e) => {
            const next = Number(e.currentTarget.value);
            if (Number.isFinite(next)) props.onChange(next);
          }}
        />
        {props.unit ? <span class="unit">{props.unit}</span> : null}
      </span>
    </label>
  );
}

export function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  format?: (value: number) => string;
  onChange: (value: number) => void;
}) {
  const shown = props.format ? props.format(props.value) : String(props.value);
  return (
    <label class="field">
      <span class="field-label">
        {props.label}
        <b class="field-value">{shown}</b>
      </span>
      <input
        class="slider"
        type="range"
        min={props.min}
        max={props.max}
        step={props.step ?? 1}
        value={props.value}
        onInput={(e) => props.onChange(Number(e.currentTarget.value))}
      />
    </label>
  );
}

export function SelectField<T extends string>(props: {
  label: string;
  value: T;
  options: readonly Choice<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <label class="field">
      <span class="field-label">{props.label}</span>
      <select class="input" value={props.value} onChange={(e) => props.onChange(e.currentTarget.value as T)}>
        {props.options.map((o) => (
          <option value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}

export function ColorField(props: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label class="field field-row">
      <span class="field-label">{props.label}</span>
      <input class="color" type="color" value={props.value} onInput={(e) => props.onChange(e.currentTarget.value)} />
    </label>
  );
}

export function LanguageChips(props: {
  value: readonly string[];
  options: readonly Choice<string>[];
  onChange: (value: string[]) => void;
}) {
  const flip = (code: string) => {
    const has = props.value.includes(code);
    const next = has ? props.value.filter((c) => c !== code) : [...props.value, code];
    props.onChange(next.length ? next : [code]);
  };
  return (
    <div class="chips">
      {props.options.map((o) => (
        <button
          type="button"
          aria-pressed={props.value.includes(o.value)}
          class={props.value.includes(o.value) ? "chip on" : "chip"}
          onClick={() => flip(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const OCR_LANGUAGES: readonly Choice<string>[] = [
  { value: "eng", label: "English" },
  { value: "ara", label: "Arabic" },
  { value: "fra", label: "French" },
  { value: "deu", label: "German" },
  { value: "spa", label: "Spanish" },
  { value: "tur", label: "Turkish" },
];

export function PasswordField(props: { label: string; value: string; onInput: (value: string) => void; hint?: string }) {
  return <TextField {...props} type="password" dir="ltr" />;
}
