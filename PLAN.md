# Free PDF plan

A free, offline Windows desktop app with every tool iLovePDF offers, at the same quality, for one person who uses it to study.

Goals, in order:
1. Every tool works and output quality matches iLovePDF as closely as free engines allow.
2. Opens fast and feels simple.
3. Never stresses the laptop.

## Hard rules for everyone working on this

### Do not disturb the user (they are studying on this PC right now)
- Never show anything on screen. No visible windows, no browsers, no `Start-Process` of apps, no `cargo tauri dev`, no running the built app with a visible window, no desktop screenshots.
- UI checks use headless Edge or headless Playwright only, writing PNGs to the scratch folder.
- Office automation must be hidden: `win32com.client.DispatchEx(...)`, `Visible = False`, `DisplayAlerts = 0`. Quit only the instance you created. Never touch an instance the user has open.

### Keep the laptop cool
- Run anything that uses real CPU through `cmd /c start /low /b /wait <command>`.
- One test file at a time. Never run the full test suite in parallel. No pytest-xdist.
- Only the app agent may compile Rust, always with `CARGO_BUILD_JOBS=2`.
- Build outputs stay outside OneDrive, in `%LOCALAPPDATA%\FreePDF-dev\`: the venv at `venv\`, Rust output at `target\`, tools at `tools\`, OCR data at `tessdata\`. `app/node_modules` must be a junction pointing there. Nothing heavy goes inside the project folder.

### Stay in bounds
- Do not copy anything from iLovePDF: no logo, icons, code, text, or engine DLLs. Match what it does and its flow, never its assets. Do not open or inspect its install folder.
- No Ollama and no paid or online AI services.
- Do not read, change or delete the user's personal files. Use generated samples.
- Do not commit. Do not install anything system wide. Python packages go in the venv with `uv pip install --python "%LOCALAPPDATA%\FreePDF-dev\venv\Scripts\python.exe"`.

### Code style
Small files, 200 to 400 lines, 800 at most. Functions under 50 lines. Organised by feature. Immutable patterns. No stray print or console.log. Comments only when the reason is not obvious. Match the surrounding code.

## Architecture

```
app/                 Tauri 2 shell and UI (Preact, TypeScript, Vite)
  src/               UI
  src-tauri/         Rust: starts the engines, relays JSON, native dialogs
engine/              Python engine (PyMuPDF and friends)
  freepdf_engine/    protocol, registry, tools/
  tests/             pytest, generated samples
```

Rust starts two hidden engine processes when the window opens, so the UI paints first:
- `viewer` runs `info`, `thumb`, `search`, `page_text`. Must stay instant.
- `jobs` runs everything else, one at a time.

## Engine protocol

One JSON object per line, UTF-8, over stdin and stdout.

Request: `{"id":"abc","tool":"merge","args":{...}}`
Cancel: `{"cancel":"abc"}`
Progress: `{"id":"abc","type":"progress","value":0.4,"message":"Page 3 of 10"}`
Result: `{"id":"abc","type":"result","outputs":[{"path":"...","size":123}],"summary":{...}}`
Error: `{"id":"abc","type":"error","code":"wrong_password","message":"..."}`

Error messages are shown to the user. Say what happened and how to fix it. Never show a stack trace. Error codes used so far: `bad_args`, `file_not_found`, `not_a_pdf`, `wrong_password`, `cancelled`, `office_missing`, `office_failed`, `tool_failed`, `unknown_tool`, `missing_resource`.

Conventions:
- Pages are 0-based in args. Page ranges from users are 1-based strings like `"1-3,7"`, parsed by `pages_spec.parse_ranges`.
- Coordinates are PDF points with the origin at the top left of the page.
- Output goes next to the first input unless `args.out_dir` is set. Use `paths.output_path(src, "compressed")`, which gives `name (compressed).pdf` and never overwrites anything.
- Password-protected input: every tool takes an optional `password`.
- Write a tool with `@tool("name")`, signature `def fn(job: Job, args: dict) -> dict`, and return `result([paths], key=value)`. Call `job.progress(...)` and `job.check_cancelled()` in loops. Raise `ToolError(code, message)` for expected failures.

## Tools and arguments

Common: `password`, `out_dir`.

### Pages
| Tool | Args |
|---|---|
| `merge` | `files: [{path, password?}]` |
| `split` | `file`, `mode: "ranges"\|"every"\|"extract_all"\|"extract"\|"size"`, `ranges`, `every`, `max_mb`, `merge_output: bool`. Several outputs are zipped into one `.zip` when `zip` is true |
| `organize` | `file`, `pages: [{source: path, page: int, rotate: int, blank?: bool}]`, the output order |
| `rotate` | `file`, `angle: 90\|180\|270`, `pages?: [int]`, default all |
| `crop` | `file`, `box: [x0,y0,x1,y1]`, `pages?: [int]` |

### Optimize
| Tool | Args |
|---|---|
| `compress` | `file`, `level: "extreme"\|"recommended"\|"less"`. Summary has `before`, `after`, `percent` |
| `repair` | `file` |
| `pdfa` | `file`, `conformance: "1b"\|"2b"\|"3b"` |
| `ocr` | `file`, `languages: ["eng","ara"]`, `pages?` |

### Into PDF
| Tool | Args |
|---|---|
| `word_to_pdf`, `ppt_to_pdf`, `excel_to_pdf` | `files: [path]`, `merge_output: bool` |
| `images_to_pdf` | `files: [path]`, `orientation: "portrait"\|"landscape"`, `page_size: "fit"\|"a4"\|"letter"`, `margin: "none"\|"small"\|"big"`, `merge_output: bool` |
| `html_to_pdf` | `source` (URL or local path), `page_size`, `orientation`, `margin`, `one_long_page: bool` |
| `scan_to_pdf` | `device?`, `dpi`, `color: bool`. Also `list_scanners` with no args |

### Out of PDF
| Tool | Args |
|---|---|
| `pdf_to_word` | `file`, `ocr: bool`, `languages` |
| `pdf_to_ppt` | `file`, `ocr: bool`, `languages` |
| `pdf_to_excel` | `file`, `ocr: bool`, `languages`, `one_sheet: bool` |
| `pdf_to_images` | `file`, `mode: "pages"\|"extract"`, `format: "jpg"\|"png"`, `dpi`, `quality`, `pages?`, `zip: bool` |
| `pdf_to_text` | `file`, `pages?` |

### Mark up
All use `items: [...]` drawn in the UI, each with `page` and coordinates in points.
| Tool | Args |
|---|---|
| `edit` | `file`, `items`: `text` (x, y, text, font, size, color, bold, italic), `image` (rect, path, rotate), `shape` (kind: rect/ellipse/line/arrow, rect, stroke, fill, width), `ink` (points, color, width), `whiteout` (rect, color) |
| `sign` | `file`, `items`: `signature` (rect, image_path), `text_field` (x, y, text, font, size). Also `make_signature` with `text`, `font`, `color` returns a PNG |
| `watermark` | `file`, `kind: "text"\|"image"`, `text`, `font`, `size`, `bold`, `italic`, `underline`, `color`, `image_path`, `position: "top-left".."bottom-right"` (nine), `mosaic: bool`, `opacity`, `rotation`, `layer: "over"\|"under"`, `from_page`, `to_page` |
| `page_numbers` | `file`, `position` (six), `margin: "small"\|"recommended"\|"big"`, `first_number`, `from_page`, `to_page`, `format` such as `"{n}"`, `"Page {n}"`, `"Page {n} of {total}"`, `facing: bool`, `font`, `size`, `bold`, `italic`, `color` |
| `redact` | `file`, `items`: `area` (page, rect), `search` (text, all matches). Must remove the content for real, not cover it. Also clears metadata when `clean_metadata` is true |
| `annotate` | `file`, `items`: highlight, underline, strikeout, note, ink, freetext. Saved as real PDF annotations |
| `compare` | `file_a`, `file_b`, `password_b?`, `mode: "text"\|"visual"`. Text mode gives per-page added and removed text with rects. Visual mode gives per-page difference images |

### Language
| Tool | Args |
|---|---|
| `translate` | `file`, `source`, `target`. Layout preserved, runs offline with Argos Translate |
| `summarize` | `file`, `length: "short"\|"medium"\|"long"`, `pages?`. Offline extractive summary. Returns text in `summary.text` and a `.txt` output |

### Viewer engine
| Tool | Args and result |
|---|---|
| `info` | `file` gives `pages`, `sizes`, `encrypted`, `needs_password`, `scanned` (bool guess), `title`, `bytes` |
| `thumb` | `file`, `page`, `width` gives a cached PNG path in `summary.path` |
| `page_text` | `file`, `page` gives `summary.text`, `summary.rtl` |
| `search` | `file`, `query` gives `summary.hits: [{page, rects}]` |

## UI

Same flow as iLovePDF, in original design:
1. Home: top bar with logo slot and category menu, a filter row (All, Organize, Optimize, Convert, Edit, Security), and a grid of tool cards with icon, name and one line.
2. Tool page: large select-files button and whole-window drag and drop.
3. Workspace: file thumbnails in the centre, options sidebar on the right, big action button at the bottom right.
4. Result: open, show in folder, and next-tool suggestions.

Also a built-in reader for studying: page view, search, thumbnails, highlight, underline, notes, drawing, print.

Look: clean, light by default, follows the Windows dark setting. Icons from `lucide-preact`. Accent colour must not be iLovePDF red. Original layout details and copy. The logo is supplied by the user later, so `app/public/logo.svg` is a plain text placeholder that can be swapped by replacing one file.

Arabic matters. File names and PDF text can be Arabic: show file names in an LTR container so the extension stays on the right, use `dir="auto"` for PDF text, and keep OCR defaulted to `eng` plus `ara`.
