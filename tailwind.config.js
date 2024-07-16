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
      colors: {
        'rate-newbie': 'gray',
        'rate-pupil': 'green',
        'rate-specialist': '#03a89e',
        'rate-expert': '#00f',
        'rate-candinate-master': '#a0a',
        'rate-master': '#ff8c00',
        'rate-international-master': '#ff8c00',
        'rate-grandmaster': 'red',
        'rate-international-grandmaster': 'red',
        'rate-legendary-grandmaster': 'red',
      },
      fontFamily: {
        consolas: ['Consolas', 'monospace'],
      }
    },
  },
  plugins: [require('@tailwindcss/typography'), require('daisyui'),],
  daisyui: {
    themes: ["light", "dark"],
  },
  purge: {
    options: {
      safelist: {
        standard: [
        'text-2xl',
        'text-3xl',
        'text-4xl',
        'text-5xl',
        'text-6xl',
        'sm:text-2xl',
        'sm:text-3xl',
        'sm:text-4xl',
        'sm:text-5xl',
        'sm:text-6xl',
        'md:text-2xl',
        'md:text-3xl',
        'md:text-4xl',
        'md:text-5xl',
        'md:text-6xl',
        'lg:text-2xl',
        'lg:text-3xl',
        'lg:text-4xl',
        'lg:text-5xl',
        'lg:text-6xl',
        ],
      },
    },
  }
}
