import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F7F6F0",
        shell: "#F2F0E8",
        card: "#FFFFFF",
        ink: "#1B1A14",
        muted: "#6E6A5B",
        faint: "#9C9786",
        line: "#E7E3D5",
        lineStrong: "#D7D2C0",
        accent: "#156B45",
        accentDeep: "#0E4D32",
        accentSoft: "#E4F0E8",
        pine: "#10402A",
        pineDeep: "#0A2E1E",
        amber: "#A8731D",
        amberSoft: "#FBF4E2",
        rust: "#A93B2A",
        rustSoft: "#FAEDE8",
      },
      fontFamily: {
        display: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(27,26,20,0.05), 0 1px 1px rgba(27,26,20,0.03)",
        lift: "0 14px 40px -16px rgba(27,26,20,0.18)",
        pop: "0 2px 6px rgba(27,26,20,0.06), 0 16px 40px -20px rgba(27,26,20,0.16)",
      },
    },
  },
  plugins: [],
};
export default config;
