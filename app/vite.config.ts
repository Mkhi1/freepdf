import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  base: "./",
  plugins: [preact()],
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  build: {
    target: "chrome110",
    sourcemap: false,
    cssCodeSplit: true,
    reportCompressedSize: false,
  },
});
