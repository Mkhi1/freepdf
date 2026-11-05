import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const OUT = join(process.env.LOCALAPPDATA ?? ".", "FreePDF-dev", "e2e");

// Headless only: the app runs in Vite, the real Python engine runs behind e2e/bridge.mjs.
export default defineConfig({
  testDir: "e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: join(OUT, "report") }]],
  outputDir: join(OUT, "results"),
  use: {
    baseURL: "http://localhost:5173",
    headless: true,
    viewport: { width: 1280, height: 820 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    { command: "node e2e/bridge.mjs", port: 5181, reuseExistingServer: true, timeout: 60_000 },
    { command: "npx vite --port 5173 --strictPort", port: 5173, reuseExistingServer: true, timeout: 60_000 },
  ],
});
