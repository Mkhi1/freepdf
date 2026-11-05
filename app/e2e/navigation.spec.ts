import { expect, expectResult, openTool, queuePick, runAction, test } from "./helpers";

test("tools page lists every tool and filters by category and search", async ({ app }) => {
  await app.goto("/#/tools");
  const cards = app.locator(".grid .card");
  await expect(cards).toHaveCount(32);
  await app.getByRole("tab", { name: "Security" }).click();
  await expect(cards).toHaveCount(5);
  await app.getByRole("tab", { name: "All" }).click();
  await app.getByPlaceholder("Find a tool").fill("word");
  await expect(cards.first()).toContainText(/Word/);
  await app.getByPlaceholder("Find a tool").fill("zzzz");
  await expect(app.locator(".empty")).toContainText("No tool matches");
});

test("every tool card opens its page", async ({ app }) => {
  await app.goto("/#/tools");
  const hrefs = await app.locator(".grid .card").evaluateAll((els) => els.map((e) => e.getAttribute("href")!));
  for (const href of hrefs) {
    await app.goto(`/${href}`);
    await expect(app.locator("h1").first()).not.toHaveText("That tool is not here");
  }
});

test("home opens a PDF straight into the reader and adds a tab", async ({ app, file }) => {
  await app.goto("/#/");
  await queuePick(app, [file("Study notes.pdf")]);
  await app.getByRole("button", { name: "Open file" }).click();
  await app.waitForURL(/#\/editor\/reader/);
  await expect(app.locator(".tabbar .tab-name")).toContainText("Study notes.pdf");
});

test("a finished job shows up in history and can be removed", async ({ app, file }) => {
  await openTool(app, "rotate", [file("Chapter two.pdf")]);
  await runAction(app);
  await expectResult(app);
  await app.goto("/#/history");
  const rows = app.locator(".hist-row");
  await expect(rows.first()).toContainText("Chapter two");
  const before = await rows.count();
  await rows.first().getByRole("button", { name: "Remove from history" }).click();
  await expect(rows).toHaveCount(before - 1);
});

test("result page offers next tools that open with the output", async ({ app, file }) => {
  await openTool(app, "merge", [file("Study notes.pdf"), file("Chapter two.pdf")]);
  await runAction(app);
  await expectResult(app);
  await app.locator(".resultpage a, .resultpage button").filter({ hasText: "Compress" }).first().click();
  await app.waitForURL(/#\/work\/compress/);
  await expect(app.locator(".fcard")).toHaveCount(1);
  await expect(app.locator(".fcard")).toContainText("(merged)");
});

test("Arabic file names keep the extension on the right", async ({ app, file }) => {
  await openTool(app, "compress", [file("ملخص عربي.pdf")]);
  await app.waitForURL(/#\/work\//);
  const name = app.locator(".fname").first();
  await expect(name).toHaveText("ملخص عربي.pdf");
  const [arabicLeft, dotLeft] = await name.evaluate((e) => {
    const node = e.firstChild!;
    const left = (i: number) => { const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + 1); return r.getBoundingClientRect().left; };
    return [left(0), left(e.textContent!.indexOf("."))];
  });
  expect(dotLeft, "the .pdf part should be drawn to the right of the Arabic words").toBeGreaterThan(arabicLeft);
});

test("merge keeps the order chosen with the keyboard", async ({ app, file }) => {
  await openTool(app, "merge", [file("Study notes.pdf"), file("Chapter two.pdf")]);
  const first = app.locator(".fcard").first();
  await expect(first).toContainText("Study notes");
  await first.focus();
  await app.keyboard.press("Alt+ArrowRight");
  await expect(app.locator(".fcard").first()).toContainText("Chapter two");
});

test("devices page shows this PC and explains a bad address", async ({ app }) => {
  await app.goto("/#/devices");
  await expect(app.locator("#share-name")).toHaveValue("Test PC");
  await app.locator("#share-ip").fill("10.0.0.99");
  await app.locator("#share-ip").press("Enter");
  await expect(app.locator(".share-error")).toBeVisible();
});

test("cancelling a running job stops it and saves nothing", async ({ app, file }) => {
  await openTool(app, "ocr", [file("Scanned page.pdf")]);
  await runAction(app);
  await app.getByRole("button", { name: "Cancel" }).click();
  await expect(app.locator(".side-foot .note")).toContainText("Stopped", { timeout: 60_000 });
});
