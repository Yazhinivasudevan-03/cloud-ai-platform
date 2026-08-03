import { existsSync, mkdirSync, copyFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

/** Copies manifest.json and icons/ into dist/ verbatim - Vite has no reason
 * to process either (no bundling/templating needed for a static manifest or
 * plain PNGs), so a plugin is simpler and more transparent than folding them
 * into the Rollup input graph. */
function copyStaticAssets(): Plugin {
  return {
    name: "copy-static-assets",
    closeBundle() {
      const outDir = resolve(rootDir, "dist");
      copyFileSync(resolve(rootDir, "manifest.json"), resolve(outDir, "manifest.json"));

      const iconsOutDir = resolve(outDir, "icons");
      mkdirSync(iconsOutDir, { recursive: true });
      const iconsSrcDir = resolve(rootDir, "icons");
      if (existsSync(iconsSrcDir)) {
        for (const file of readdirSync(iconsSrcDir)) {
          copyFileSync(resolve(iconsSrcDir, file), resolve(iconsOutDir, file));
        }
      }
    },
  };
}

export default defineConfig({
  root: "src",
  publicDir: false,
  plugins: [copyStaticAssets()],
  build: {
    outDir: "../dist",
    emptyOutDir: true,
    target: "es2022",
    rollupOptions: {
      input: {
        popup: resolve(rootDir, "src/popup/popup.html"),
        background: resolve(rootDir, "src/background/service-worker.ts"),
      },
      output: {
        entryFileNames: (chunk) =>
          chunk.name === "background" ? "background/service-worker.js" : "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
