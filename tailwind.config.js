/** @type {import('tailwindcss').Config} */
export default {
  content: ["templates/**/*.{html,js}"],
  theme: {
    extend: {},
  },
  plugins: [require('daisyui'),],
  daisyui: {
    themes: ["light", "dark"],
  },
}
