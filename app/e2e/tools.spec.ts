import { existsSync, statSync } from "node:fs";
import type { Page } from "@playwright/test";
import { expect, expectResult, lastCall, lastReply, openTool, pdfFacts, runAction, test } from "./helpers";
import type { EngineReply } from "./helpers";

interface Case {
  tool: string;
  files: string[];
  setup?: (page: Page) => Promise<void>;
  check: (reply: EngineReply, page: Page) => void | Promise<void>;
  timeout?: number;
}

function firstOutput(reply: EngineReply): string {
  expect(reply.error, JSON.stringify(reply.error)).toBeUndefined();
  const path = reply.value!.outputs[0].path;
  expect(existsSync(path), `${path} should exist`).toBe(true);
  expect(statSync(path).size).toBeGreaterThan(0);
  return path;
}

const CASES: Case[] = [
  { tool: "merge", files: ["Study notes.pdf", "Chapter two.pdf"], check: (r) => expect(pdfFacts(firstOutput(r)).pages).toBe(9) },
  {
    tool: "split", files: ["Study notes.pdf"],
    setup: async (p) => { await p.getByLabel("Pages").fill("1-2, 5"); },
    check: (r) => { expect(firstOutput(r)).toMatch(/\.zip$/); expect(r.value!.summary.parts ?? r.value!.summary.files).toBeTruthy(); },
  },
  {
    tool: "rotate", files: ["Study notes.pdf"],
    check: (r) => { const f = pdfFacts(firstOutput(r)); expect(f.pages).toBe(6); expect(f.width).toBeGreaterThan(f.height); },
  },
  { tool: "compress", files: ["Photos heavy.pdf"], check: (r) => { firstOutput(r); expect(r.value!.summary.after).toBeLessThanOrEqual(r.value!.summary.before); } },
  { tool: "repair", files: ["Study notes.pdf"], check: (r) => expect(pdfFacts(firstOutput(r)).pages).toBe(6) },
  { tool: "ocr", files: ["Scanned page.pdf"], timeout: 170_000, check: (r) => expect(pdfFacts(firstOutput(r)).text).toMatch(/Cells|basic|unit/i) },
  { tool: "word_to_pdf", files: ["Essay.docx"], check: (r) => expect(pdfFacts(firstOutput(r)).text).toContain("Study Notes") },
  { tool: "ppt_to_pdf", files: ["Slides.pptx"], check: (r) => expect(pdfFacts(firstOutput(r)).text).toContain("Quarterly Review") },
  { tool: "excel_to_pdf", files: ["Marks.xlsx"], check: (r) => expect(pdfFacts(firstOutput(r)).text).toContain("Amal") },
  { tool: "images_to_pdf", files: ["Photo one.jpg", "Photo two.png"], check: (r) => expect(pdfFacts(firstOutput(r)).pages).toBe(2) },
  { tool: "html_to_pdf", files: ["Page.html"], check: (r) => expect(pdfFacts(firstOutput(r)).text).toContain("Renewable Energy") },
  { tool: "pdf_to_word", files: ["Study notes.pdf"], check: (r) => expect(firstOutput(r)).toMatch(/\.docx$/) },
  { tool: "pdf_to_ppt", files: ["Study notes.pdf"], check: (r) => expect(firstOutput(r)).toMatch(/\.pptx$/) },
  { tool: "pdf_to_excel", files: ["Study notes.pdf"], check: (r) => expect(firstOutput(r)).toMatch(/\.xlsx$/) },
  { tool: "pdf_to_images", files: ["Chapter two.pdf"], check: (r) => expect(firstOutput(r)).toMatch(/\.(zip|jpg)$/) },
  { tool: "pdf_to_text", files: ["Study notes.pdf"], check: (r) => expect(firstOutput(r)).toMatch(/\.txt$/) },
  {
    tool: "watermark", files: ["Study notes.pdf"],
    check: (r) => expect(pdfFacts(firstOutput(r)).text.length).toBeGreaterThan(0),
  },
  { tool: "page_numbers", files: ["Study notes.pdf"], check: (r) => expect(pdfFacts(firstOutput(r)).text).toMatch(/\b6\b/) },
  { tool: "summarize", files: ["Study notes.pdf"], check: async (r, p) => { firstOutput(r); await expect(p.locator(".resultpage")).toContainText(/zebra|Chapter|Body/i); } },
  { tool: "translate", files: ["Study notes.pdf"], timeout: 170_000, check: (r) => expect(pdfFacts(firstOutput(r)).text).toMatch(/[؀-ۿ]/) },
  {
    tool: "protect", files: ["Study notes.pdf"],
    setup: async (p) => { await p.getByLabel("Password", { exact: true }).fill("abc123"); await p.getByLabel("Type it again").fill("abc123"); },
    check: (r) => { const out = firstOutput(r); expect(pdfFacts(out).encrypted).toBe(true); expect(pdfFacts(out, "abc123").pages).toBe(6); },
  },
];

test("pdfa converts, or explains that Ghostscript is missing", async ({ app, file }) => {
  await openTool(app, "pdfa", [file("Study notes.pdf")]);
  await runAction(app);
  const outcome = await Promise.race([
    app.waitForURL(/#\/result\//, { timeout: 120_000 }).then(() => "done"),
    app.locator(".side-foot .error").waitFor({ timeout: 120_000 }).then(() => "error"),
  ]);
  if (outcome === "error") {
    await expect(app.locator(".side-foot .error")).toContainText("Ghostscript");
    test.info().annotations.push({ type: "gap", description: "Ghostscript is not installed, so PDF/A cannot run" });
    return;
  }
  expect(pdfFacts(firstOutput(await lastReply(app, "pdfa"))).pages).toBe(6);
});

for (const c of CASES) {
  test(`${c.tool} runs end to end`, async ({ app, file }) => {
    test.setTimeout((c.timeout ?? 120_000) + 30_000);
    await openTool(app, c.tool, c.files.map(file));
    await app.waitForURL(/#\/work\//);
    await expect(app.locator(".side-body")).not.toContainText("Loading options");
    await c.setup?.(app);
    await runAction(app);
    await expectResult(app, c.timeout ?? 120_000);
    await expect(app.locator(".resultpage")).toContainText("Done");
    await c.check(await lastReply(app, c.tool), app);
    expect((await lastCall(app, c.tool)).tool).toBe(c.tool);
  });
}
