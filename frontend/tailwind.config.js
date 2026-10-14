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
        ops: {
          bg: "#0a0d12",
          panel: "#111722",
          panel2: "#0d131b",
          border: "#1e2838",
          borderStrong: "#2a3850",
          accent: "#f5a524",
          accentDim: "#c17f12",
        },
        status: {
          critical: "#ef4444",
          high: "#f5a524",
          medium: "#eab308",
          low: "#64748b",
          ok: "#22c55e",
        },
      },
      letterSpacing: {
        widest2: "0.14em",
      },
    },
  },
  plugins: [],
};
