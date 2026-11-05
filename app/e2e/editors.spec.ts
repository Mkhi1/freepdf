import type { Page } from "@playwright/test";
import { expect, expectResult, lastReply, openTool, pdfFacts, test } from "./helpers";

/** Drags across the page overlay, from and to fractions of its size. */
async function drag(page: Page, from: [number, number], to: [number, number]): Promise<void> {
  const box = (await page.locator(".ed-overlay").first().boundingBox())!;
  await page.mouse.move(box.x + box.width * from[0], box.y + box.height * from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * ((from[0] + to[0]) / 2), box.y + box.height * ((from[1] + to[1]) / 2), { steps: 4 });
  await page.mouse.move(box.x + box.width * to[0], box.y + box.height * to[1], { steps: 4 });
  await page.mouse.up();
}

async function clickPage(page: Page, at: [number, number]): Promise<void> {
  const box = (await page.locator(".ed-overlay").first().boundingBox())!;
  await page.mouse.click(box.x + box.width * at[0], box.y + box.height * at[1]);
}

async function openEditor(page: Page, id: string, files: string[]): Promise<void> {
  await openTool(page, id, files);
  await page.waitForURL(new RegExp(`#/editor/${id}`));
}

async function pageReady(page: Page): Promise<void> {
  await expect(page.locator(".ed-bg").first()).toBeVisible({ timeout: 30_000 });
}

async function save(page: Page): Promise<void> {
  const action = page.locator(".side-foot .btn.action");
  await expect(action).toBeEnabled();
  await action.click();
  await expectResult(page);
}

function output(reply: Awaited<ReturnType<typeof lastReply>>): string {
  expect(reply.error, JSON.stringify(reply.error)).toBeUndefined();
  return reply.value!.outputs[0].path;
}

test("edit: rectangle and drawing are saved into the PDF", async ({ app, file }) => {
  await openEditor(app, "edit", [file("Study notes.pdf")]);
  await pageReady(app);
  await app.getByRole("button", { name: "Rectangle" }).click();
  await drag(app, [0.2, 0.5], [0.6, 0.6]);
  await app.getByRole("button", { name: "Draw" }).click();
  await drag(app, [0.2, 0.7], [0.7, 0.75]);
  await save(app);
  const out = output(await lastReply(app, "edit"));
  expect(pdfFacts(out).pages).toBe(6);
});

test("annotate: highlight and note become real annotations", async ({ app, file }) => {
  await openEditor(app, "annotate", [file("Study notes.pdf")]);
  await pageReady(app);
  await app.getByRole("button", { name: "Highlight" }).click();
  await drag(app, [0.12, 0.155], [0.5, 0.17]);
  await app.getByRole("button", { name: "Note" }).click();
  await clickPage(app, [0.8, 0.3]);
  await save(app);
  expect(pdfFacts(output(await lastReply(app, "annotate"))).annots).toBeGreaterThanOrEqual(2);
});

test("redact: found words are removed for real", async ({ app, file }) => {
  await openEditor(app, "redact", [file("Study notes.pdf")]);
  await pageReady(app);
  await app.getByLabel("Text to find").fill("zebra1");
  await app.getByLabel("Text to find").press("Enter");
  await app.getByRole("button", { name: /Mark all/ }).click();
  await drag(app, [0.1, 0.25], [0.5, 0.3]);
  await app.locator(".side-foot .btn.action").click();
  await app.getByRole("button", { name: "Yes, redact for good" }).click();
  await expectResult(app);
  const text = pdfFacts(output(await lastReply(app, "redact"))).text;
  expect(text).not.toContain("zebra1");
  expect(text).toContain("zebra2");
});

test("crop: page gets the size typed in", async ({ app, file }) => {
  await openEditor(app, "crop", [file("Study notes.pdf")]);
  await pageReady(app);
  await app.getByLabel("Left").fill("50");
  await app.getByLabel("Left").press("Tab");
  await app.getByLabel("Right").fill("450");
  await app.getByLabel("Right").press("Tab");
  await save(app);
  const facts = pdfFacts(output(await lastReply(app, "crop")));
  expect(Math.round(facts.width)).toBe(400);
});

test("sign: a typed signature is placed on the page", async ({ app, file }) => {
  await openEditor(app, "sign", [file("Study notes.pdf")]);
  await pageReady(app);
  await app.getByRole("radio", { name: "Type", exact: true }).click();
  await app.getByLabel("Your name").fill("Sara Ali");
  await app.getByRole("button", { name: "Make signature" }).click();
  await app.getByRole("button", { name: "Place this signature" }).first().click();
  await clickPage(app, [0.6, 0.45]);
  await save(app);
  expect(pdfFacts(output(await lastReply(app, "sign"))).pages).toBe(6);
});

test("organize: delete and rotate pages", async ({ app, file }) => {
  await openEditor(app, "organize", [file("Study notes.pdf")]);
  const tiles = app.getByRole("option");
  await expect(tiles).toHaveCount(6);
  await tiles.nth(1).click();
  await app.getByRole("button", { name: "Delete" }).click();
  await expect(tiles).toHaveCount(5);
  await tiles.nth(0).click();
  await app.getByRole("button", { name: "Rotate right" }).click();
  await app.locator(".btn.action, .btn.big.primary").last().click();
  await expectResult(app);
  const facts = pdfFacts(output(await lastReply(app, "organize")));
  expect(facts.pages).toBe(5);
  expect(facts.width).toBeGreaterThan(facts.height);
});

test("compare: differences between two versions are listed", async ({ app, file }) => {
  await openEditor(app, "compare", [file("Study notes.pdf"), file("Study notes v2.pdf")]);
  await app.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(app.getByLabel("Changes").first()).toContainText(/version two|added/i, { timeout: 60_000 });
});

test("reader: opens, searches and jumps between matches", async ({ app, file }) => {
  await openEditor(app, "reader", [file("Study notes.pdf")]);
  await expect(app.locator("img").first()).toBeVisible({ timeout: 30_000 });
  await app.getByLabel("Search in this PDF").fill("zebra3");
  await app.getByLabel("Search in this PDF").press("Enter");
  await expect(app.locator(".reader, .page").first()).toContainText(/1 of 1|1\/1|match/i, { timeout: 20_000 });
});

test("locked file asks for the password and then works", async ({ app, file }) => {
  await openTool(app, "compress", [file("Locked notes.pdf")]);
  await app.waitForURL(/#\/work\//);
  const pw = app.locator('input[type="password"]').first();
  await expect(pw).toBeVisible({ timeout: 20_000 });
  await pw.fill("wrong");
  await pw.press("Enter");
  await expect(app.locator(".stage")).toContainText(/wrong|not right|try again|password/i);
  await pw.fill("secret1");
  await pw.press("Enter");
  await app.locator(".side-foot .btn.action").click();
  await expectResult(app);
});

test("a file that is not a PDF is refused politely", async ({ app, file }) => {
  await app.goto("/#/tool/compress");
  await app.evaluate((p) => (window as any).__e2e.drop([p]), file("notes.txt"));
  await expect(app.locator(".notice")).toBeVisible();
});
