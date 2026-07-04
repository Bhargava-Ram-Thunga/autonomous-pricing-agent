/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          navy: '#053484',
          blue: '#095FF0',
          yellow: '#FAE823',
          'light-blue': '#E6EFFE',
        },
      },
    },
  },
  plugins: [],
}
