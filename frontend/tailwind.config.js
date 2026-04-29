/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'brand-red': '#800000',
        'brand-orange': '#ffa500',
        'brand-pink': '#ff6b6b',
      },
    },
  },
  plugins: [],
}
