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
        /* 60% — Backgrounds & surfaces (theme-aware) */
        bg: {
          base: "rgb(var(--bg-base) / <alpha-value>)",
          surface: "rgb(var(--bg-surface) / <alpha-value>)",
          elevated: "rgb(var(--bg-elevated) / <alpha-value>)",
          reader: "rgb(var(--bg-reader) / <alpha-value>)",
        },

        /* 30% — Text & primary accent (theme-aware) */
        text: {
          primary: "rgb(var(--text-primary) / <alpha-value>)",
          muted: "rgb(var(--text-muted) / <alpha-value>)",
          subtle: "rgb(var(--text-subtle) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          hover: "rgb(var(--accent-hover) / <alpha-value>)",
          light: "rgb(var(--accent-light) / <alpha-value>)",
        },

        /* Book-spine tints (decorative, constant across themes) */
        cover: {
          1: "rgb(var(--cover-1) / <alpha-value>)",
          2: "rgb(var(--cover-2) / <alpha-value>)",
          3: "rgb(var(--cover-3) / <alpha-value>)",
          4: "rgb(var(--cover-4) / <alpha-value>)",
        },

        /* Shelf spine cloth palette (constant across themes) */
        spine: {
          1: "rgb(var(--spine-1) / <alpha-value>)",
          2: "rgb(var(--spine-2) / <alpha-value>)",
          3: "rgb(var(--spine-3) / <alpha-value>)",
          4: "rgb(var(--spine-4) / <alpha-value>)",
          5: "rgb(var(--spine-5) / <alpha-value>)",
          6: "rgb(var(--spine-6) / <alpha-value>)",
          7: "rgb(var(--spine-7) / <alpha-value>)",
          8: "rgb(var(--spine-8) / <alpha-value>)",
          ink: "rgb(var(--spine-ink) / <alpha-value>)",
          paper: "rgb(var(--spine-paper) / <alpha-value>)",
        },

        /* 10% — Coverage (amber→green ramp, constant across themes) */
        coverage: {
          none: "rgb(var(--coverage-none) / <alpha-value>)",
          low: "rgb(var(--coverage-low) / <alpha-value>)",
          mid: "rgb(var(--coverage-mid) / <alpha-value>)",
          high: "rgb(var(--coverage-high) / <alpha-value>)",
          connective: "rgb(var(--coverage-connective) / <alpha-value>)",
        },

        /* 10% — Semantic states (constant) */
        state: {
          error: "rgb(var(--state-error) / <alpha-value>)",
          success: "rgb(var(--state-success) / <alpha-value>)",
          warning: "rgb(var(--state-warning) / <alpha-value>)",
        },

        /* Borders (theme-aware) */
        border: {
          DEFAULT: "rgb(var(--border-default) / <alpha-value>)",
          subtle: "rgb(var(--border-subtle) / <alpha-value>)",
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
