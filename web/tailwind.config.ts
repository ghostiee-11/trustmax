import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#FBFAF6",
        card: "#FFFFFF",
        ink: "#17170F",
        muted: "#6E6A5C",
        line: "#E6E2D6",
        accent: "#12734A",
        accentSoft: "#E3F0E8",
        amber: "#B7791F",
        rust: "#A63D2F",
      },
      fontFamily: {
        display: ["var(--font-display)", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(23,23,15,0.04), 0 1px 0 rgba(23,23,15,0.02)",
        lift: "0 8px 30px rgba(23,23,15,0.08)",
      },
    },
  },
  plugins: [],
};
export default config;
