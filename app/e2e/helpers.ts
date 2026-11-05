import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { test as base, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

const DEV = join(process.env.LOCALAPPDATA ?? ".", "FreePDF-dev");
const PYTHON = join(DEV, "venv", "Scripts", "python.exe");
const SAMPLES = join(DEV, "e2e", "samples");
const SHIM = resolve(import.meta.dirname, "tauri-shim.js");

/** Sample files, rebuilt once per run, copied into a fresh folder per test so outputs never collide. */
export function samplesFor(testName: string): (name: string) => string {
  if (!existsSync(join(SAMPLES, "Study notes.pdf"))) {
    execFileSync(PYTHON, ["-X", "utf8", "-W", "ignore", resolve(import.meta.dirname, "make_samples.py"), SAMPLES], { windowsHide: true });
  }
  const folder = join(DEV, "e2e", "work", testName.replace(/[^\w]+/g, "_").slice(0, 60));
  rmSync(folder, { recursive: true, force: true });
  mkdirSync(folder, { recursive: true });
  cpSync(SAMPLES, folder, { recursive: true });
  return (name: string) => join(folder, name);
}

export interface EngineCall {
  tool: string;
  args: Record<string, unknown>;
}

export const test = base.extend<{ app: Page; file: (name: string) => string }>({
  app: async ({ page }, use) => {
    await page.addInitScript({ path: SHIM });
    const problems: string[] = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error" && !/favicon|ERR_FILE_NOT_FOUND/.test(m.text())) problems.push(`console: ${m.text()}`);
    });
    await use(page);
    expect(problems, "the page should not log errors").toEqual([]);
  },
  file: async ({}, use, info) => {
    await use(samplesFor(info.title));
  },
});

export { expect };

/** Queues what the next native file dialog returns. */
export async function queuePick(page: Page, paths: string[]): Promise<void> {
  await page.evaluate((p) => (window as any).__e2e.picks.push(p), paths);
}

export async function calls(page: Page): Promise<EngineCall[]> {
  return page.evaluate(() => (window as any).__e2e.calls);
}

/** Opens a tool page and chooses files through the (stubbed) native picker. */
export async function openTool(page: Page, id: string, paths: string[]): Promise<void> {
  await page.goto(`/#/tool/${id}`);
  await queuePick(page, paths);
  await page.locator(".dropzone .btn.primary").first().click();
}

/** Waits until every file card has opened, then presses the big action button. */
export async function runAction(page: Page): Promise<void> {
  const action = page.locator(".side-foot .btn.action");
  await expect(action).toBeEnabled({ timeout: 60_000 });
  await action.click();
}

export async function expectResult(page: Page, timeout = 150_000): Promise<string> {
  await page.waitForURL(/#\/result\//, { timeout });
  const body = page.locator(".page").first();
  await expect(body).toBeVisible();
  return (await body.innerText()).trim();
}

export interface EngineReply {
  tool: string;
  value?: { outputs: Array<{ path: string; size?: number }>; summary: Record<string, any> };
  error?: { code: string; message: string };
}

export async function lastReply(page: Page, tool: string): Promise<EngineReply> {
  const list: EngineReply[] = (await page.evaluate(() => (window as any).__e2e.results)).filter((r: EngineReply) => r.tool === tool);
  expect(list.length, `expected a ${tool} reply`).toBeGreaterThan(0);
  return list[list.length - 1];
}

export async function lastCall(page: Page, tool: string): Promise<EngineCall> {
  const list = (await calls(page)).filter((c) => c.tool === tool);
  expect(list.length, `expected a ${tool} call`).toBeGreaterThan(0);
  return list[list.length - 1];
}

export interface PdfFacts {
  pages: number;
  encrypted: boolean;
  text: string;
  annots: number;
  width: number;
  height: number;
}

/** Reads an output PDF with PyMuPDF so tests check the real file, not just what the UI says. */
export function pdfFacts(path: string, password = ""): PdfFacts {
  const script = [
    "import json,sys,pymupdf",
    "d=pymupdf.open(sys.argv[1]); enc=d.needs_pass",
    "ok=not enc or d.authenticate(sys.argv[2])",
    "ok or (print(json.dumps({'pages':0,'encrypted':True,'text':'','annots':0,'width':0,'height':0})), sys.exit())",
    "print(json.dumps({'pages':d.page_count,'encrypted':bool(enc),'text':''.join(p.get_text() for p in d)[:4000],",
    "'annots':sum(len(list(p.annots())) for p in d),'width':d[0].rect.width,'height':d[0].rect.height}))",
  ].join("\n");
  const out = execFileSync(PYTHON, ["-X", "utf8", "-W", "ignore", "-c", script, path, password], { windowsHide: true });
  return JSON.parse(out.toString("utf8"));
}
