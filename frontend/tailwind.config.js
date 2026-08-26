/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      width: {
        70: '17.5rem',
      },
      borderWidth: {
        3: '3px',
      },
      animation: {
        'slide-in': 'slideIn 0.25s ease',
        'fade-in': 'fadeIn 0.15s ease',
      },
      keyframes: {
        slideIn: {
          from: { transform: 'translateY(8px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
