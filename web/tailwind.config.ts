import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      /* ── Typography ─────────────────────────────────── */
      fontFamily: {
        heading: ["Nunito", "sans-serif"],
        body: ["Lora", "serif"],
      },
      fontSize: {
        /* Modular scale 1.25 (major third) */
        "body-sm": ["0.75rem", { lineHeight: "1.5", fontWeight: "400" }],
        body: ["0.875rem", { lineHeight: "1.6", fontWeight: "400" }],
        "body-lg": ["1rem", { lineHeight: "1.75", fontWeight: "400" }],
        "h6": ["1rem", { lineHeight: "1.4", fontWeight: "600" }],
        "h5": ["1.125rem", { lineHeight: "1.4", fontWeight: "600" }],
        "h4": ["1.25rem", { lineHeight: "1.3", fontWeight: "600" }],
        "h3": ["1.5rem", { lineHeight: "1.25", fontWeight: "700" }],
        "h2": ["1.875rem", { lineHeight: "1.2", fontWeight: "700" }],
        "h1": ["2.25rem", { lineHeight: "1.1", fontWeight: "700" }],
        display: ["2.875rem", { lineHeight: "1.05", fontWeight: "700" }],
      },

      /* ── 60/30/10 Color Palette (dark only) ─────────── */
      colors: {
        /* 60% — Backgrounds & surfaces */
        bg: {
          base: "#0E0E0F",
          surface: "#161618",
          elevated: "#1E1E21",
          reader: "#131314",
        },

        /* 30% — Text & primary accent */
        text: {
          primary: "#F0EEE9",
          muted: "#9C9BA0",
          subtle: "#6B6A6F",
        },
        accent: {
          DEFAULT: "#7C5CFC",
          hover: "#8E74FF",
          light: "#A99BFF",
        },

        /* 10% — Coverage (amber→green ramp, exclusive use) */
        coverage: {
          none: "#252528",
          low: "#92400E",
          mid: "#D97706",
          high: "#4ADE80",
          connective: "#1E1E21",
        },

        /* 10% — Semantic states */
        state: {
          error: "#E05252",
          success: "#4ADE80",
          warning: "#F59E0B",
        },

        /* Borders */
        border: {
          DEFAULT: "#252528",
          subtle: "#1C1C1F",
        },
      },

      /* ── Border Radius ─────────────────────────────── */
      borderRadius: {
        sm: "0.25rem",
        md: "0.375rem",
        lg: "0.5rem",
        xl: "0.75rem",
      },

      /* ── Spacing ───────────────────────────────────── */
      spacing: {
        rail: "48px",
        panel: "280px",
        "panel-right": "240px",
      },

      /* ── Animation ─────────────────────────────────── */
      animation: {
        "coverage-fill": "coverage-fill 300ms ease-out",
        "panel-in": "panel-in 200ms ease-in-out",
        "panel-out": "panel-out 200ms ease-in-out",
      },
      keyframes: {
        "coverage-fill": {
          from: { opacity: "0.4" },
          to: { opacity: "1" },
        },
        "panel-in": {
          from: { width: "0", opacity: "0" },
          to: { width: "280px", opacity: "1" },
        },
        "panel-out": {
          from: { width: "280px", opacity: "1" },
          to: { width: "0", opacity: "0" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
