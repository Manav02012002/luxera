import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@luxera/luxera-ui": fileURLToPath(new URL("../../packages/luxera-ui/src/index.ts", import.meta.url)),
    },
  },
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
});
