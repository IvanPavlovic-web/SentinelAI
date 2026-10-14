/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        // Strict black/white/gray palette — no hue anywhere in the UI.
        // Hierarchy and urgency are carried by brightness, weight and
        // borders instead of color.
        ops: {
          bg: "#050505",
          panel: "#111111",
          panel2: "#0a0a0a",
          border: "#262626",
          borderStrong: "#404040",
          accent: "#ffffff",
          accentDim: "#cccccc",
        },
        status: {
          critical: "#ffffff",
          high: "#d4d4d4",
          medium: "#a3a3a3",
          low: "#6b7280",
          ok: "#e5e5e5",
        },
      },
      letterSpacing: {
        widest2: "0.14em",
      },
    },
  },
  plugins: [],
};
