import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Official BMT Broadway yellow for N/Q/R/W
        "mta-yellow": "#F6BC26",
      },
      fontFamily: {
        // System font first (SF Pro on the Mac, with its optical sizes and
        // tracking tables). The Pi has no SF, so fall back to the bundled
        // Inter Variable — the closest open stand-in — before anything else.
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "Inter Variable",
          "Inter",
          "system-ui",
          "sans-serif",
        ],
      },
      keyframes: {
        fade: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        // The outgoing photo dissolves away while the new one materializes.
        "fade-out": {
          "0%": { opacity: "1" },
          "100%": { opacity: "0" },
        },
        // Photos and panels "materialize": opacity, scale and blur arrive
        // together so the surface reads as a real thing settling into place
        // rather than a flat fade.
        materialize: {
          "0%": { opacity: "0", transform: "scale(1.03)", filter: "blur(12px)" },
          "100%": { opacity: "1", transform: "scale(1)", filter: "blur(0)" },
        },
        // A changed value (train minutes, temperature) slides up into place.
        settle: {
          "0%": { opacity: "0", transform: "translateY(0.25em)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        fade: "fade 600ms cubic-bezier(0.22, 1, 0.36, 1)",
        "fade-slow": "fade 2400ms cubic-bezier(0.22, 1, 0.36, 1)",
        "fade-out": "fade-out 1000ms cubic-bezier(0.22, 1, 0.36, 1) both",
        materialize: "materialize 1600ms cubic-bezier(0.22, 1, 0.36, 1) both",
        settle: "settle 500ms cubic-bezier(0.22, 1, 0.36, 1) both",
      },
    },
  },
  plugins: [],
} satisfies Config;
