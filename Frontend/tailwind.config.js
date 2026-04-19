/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        void: "#FBF3EE",
        midnight: "#F7EEF8",
        panel: "#FFF8F1",
        edge: "#DBCEE9",
        ink: "#43395C",
        muted: "#7E739A",
        accent: "#8B76E8",
        accentSoft: "#B8A8F2",
        teal: "#5FB39D",
        warn: "#E5C06A",
        cream: "#FFF9F2",
        blush: "#F8EEF8",
        lilac: "#ECE2FF",
        support: "#A195DA",
      },
      boxShadow: {
        glow: "0 12px 38px rgba(139, 118, 232, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.66)",
        panel: "0 16px 44px rgba(137, 113, 189, 0.19), 0 3px 8px rgba(96, 73, 148, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.76)",
      },
      fontFamily: {
        sans: ["Manrope", "Nunito Sans", "Segoe UI", "sans-serif"],
        mono: ["Sora", "Manrope", "sans-serif"],
      },
      backgroundImage: {
        grain:
          "radial-gradient(circle at 18% 9%, rgba(212, 191, 255, 0.22), rgba(255, 243, 235, 0) 48%), radial-gradient(circle at 72% 86%, rgba(248, 223, 170, 0.19), rgba(255, 243, 235, 0) 42%)",
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "0.8" },
          "50%": { opacity: "1" },
        },
        floatAura: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
      animation: {
        pulseGlow: "pulseGlow 4.2s ease-in-out infinite",
        floatAura: "floatAura 8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
