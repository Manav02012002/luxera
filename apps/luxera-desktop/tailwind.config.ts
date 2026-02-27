import type { Config } from "tailwindcss";
import { luxeraPreset } from "../../packages/luxera-ui/src/tailwind-preset";

export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../../packages/luxera-ui/src/**/*.{ts,tsx}",
  ],
  presets: [luxeraPreset],
  plugins: [],
} satisfies Config;
