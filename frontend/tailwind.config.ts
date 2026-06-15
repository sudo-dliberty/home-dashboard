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
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Inter",
          "SF Pro Display",
          "system-ui",
          "sans-serif",
        ],
      },
      keyframes: {
        fade: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        blink: {
          "0%, 49%": { opacity: "1" },
          "50%, 100%": { opacity: "0" },
        },
        // MTA countdown-clock-style update pulse on the trains panel.
        // Brief white wash plus a small scale "snap" to draw the eye.
        flash: {
          "0%":   { backgroundColor: "rgba(255,255,255,0)" },
          "12%":  { backgroundColor: "rgba(255,255,255,0.22)" },
          "100%": { backgroundColor: "rgba(255,255,255,0)" },
        },
      },
      animation: {
        fade: "fade 600ms ease-out",
        blink: "blink 1s linear infinite",
        flash: "flash 700ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
