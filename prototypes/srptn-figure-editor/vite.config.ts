import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "../../src/srptn/common/components/figure_editor_dist",
    emptyOutDir: true,
    lib: {
      entry: "src/embed/index.tsx",
      formats: ["es"],
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: "index-[hash].js",
        chunkFileNames: "index-[hash].js",
        assetFileNames: "index-[hash][extname]",
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
