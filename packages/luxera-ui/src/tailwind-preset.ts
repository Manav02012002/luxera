import type { Config } from "tailwindcss";

export const luxeraPreset: Pick<Config, "theme"> = {
  theme: {
    extend: {
      colors: {
        base: "#0f1318",
        panel: "#141a21",
        panelSoft: "#1a232d",
        border: "#253141",
        text: "#d8e2ef",
        muted: "#8c9db0",
        accent: "#6ea6ff",
      },
      borderRadius: {
        sm: "0.375rem",
        md: "0.5rem",
        lg: "0.75rem",
        xl: "1rem",
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem",
      },
      boxShadow: {
        calm: "0 10px 40px rgba(0, 0, 0, 0.35)",
      },
      fontFamily: {
        sans: ["Sora", "Inter", "Segoe UI", "sans-serif"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.875rem", { lineHeight: "1.25rem" }],
        base: ["1rem", { lineHeight: "1.5rem" }],
      },
    },
  },
};

export default luxeraPreset;
