/** @type {import('tailwindcss').Config} */
export default {
  content: ["templates/**/*.{html,js}"],
  theme: {
    extend: {
      fontFamily: {
        'sans': ['Lato', 'Roboto', 'Helvetica', 'Arial', 'sans-serif']
      }
    },
  },
  plugins: [require('daisyui'),],
  daisyui: {
    themes: ["light", "dark"],
  },
}