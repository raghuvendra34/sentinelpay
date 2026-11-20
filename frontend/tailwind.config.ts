import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#EAF0E6", // pale analysis-paper green, the page
        sheet: "#F8FAF5", // the journal sheet
        ink: "#16252B",
        muted: "#58696E",
        rule: "#C4D0C6",
        teal: { DEFAULT: "#1D5C5A", soft: "#D9E8E4" },
        debit: { DEFAULT: "#A63A2E", soft: "#F5E1DD" },
        credit: { DEFAULT: "#2D7048", soft: "#DCEDE1" },
        flag: { DEFAULT: "#9A6410", soft: "#F3E8CC" },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "ui-serif", "Georgia", "serif"],
      },
      keyframes: {
        post: { "0%": { backgroundColor: "#BFD9D3" }, "100%": { backgroundColor: "transparent" } },
      },
      animation: { post: "post 1.8s ease-out 1" },
    },
  },
  plugins: [],
};
export default config;
