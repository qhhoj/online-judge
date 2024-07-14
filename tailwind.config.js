/** @type {import('tailwindcss').Config} */
export default {
  content: ["templates/**/*.{html,js}"],
  theme: {
    extend: {
      fontFamily: {
        'sans': ['Lato', 'Roboto', 'Helvetica', 'Arial', 'sans-serif']
      },
      backgroundImage: {
        'light-blue-pink-gradient': 'radial-gradient(circle, rgba(238,174,202,1) 0%, rgba(148,187,233,1) 100%)',
        'dark-blue-pink-gradient': 'radial-gradient(circle, rgba(63,94,251,1) 0%, rgba(252,70,107,1) 100%);',
      },
    },
  },
  plugins: [require('@tailwindcss/typography'), require('daisyui'),],
  daisyui: {
    themes: ["light", "dark"],
  },
}
