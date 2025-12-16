/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./pulse/**/*.py",
    "./static/**/*.js",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      // PULSE Brand Colors - Extracted from Logo
      colors: {
        pulse: {
          blue: '#0073E6',      // Electric blue
          purple: '#7C00E6',     // Vibrant purple
          orange: '#FF7200',     // Bright orange
          navy: '#0A0F3A',       // Dark navy background
          navyLight: '#141B4D',  // Lighter navy
          navyLighter: '#1E2560', // Even lighter navy
        },
        // Semantic colors
        bg: {
          primary: '#0A0F3A',
          secondary: '#141B4D',
          tertiary: '#1E2560',
        },
        text: {
          primary: '#FFFFFF',
          secondary: '#B3B8D0',
          muted: '#8088B0',
        },
      },
      backgroundImage: {
        'pulse-gradient': 'linear-gradient(135deg, #0073E6 0%, #7C00E6 50%, #FF7200 100%)',
        'pulse-gradient-horizontal': 'linear-gradient(90deg, #0073E6 0%, #7C00E6 50%, #FF7200 100%)',
        'pulse-gradient-vertical': 'linear-gradient(180deg, #0073E6 0%, #7C00E6 50%, #FF7200 100%)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Poppins', 'Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        'pulse': '1rem',
        'pulse-lg': '1.5rem',
        'pulse-xl': '2rem',
      },
      boxShadow: {
        'pulse': '0 0 20px rgba(0, 115, 230, 0.4), 0 0 40px rgba(124, 0, 230, 0.2), 0 0 60px rgba(255, 114, 0, 0.1)',
        'pulse-sm': '0 0 10px rgba(0, 115, 230, 0.3), 0 0 20px rgba(124, 0, 230, 0.15)',
        'pulse-lg': '0 0 30px rgba(0, 115, 230, 0.5), 0 0 60px rgba(124, 0, 230, 0.3), 0 0 90px rgba(255, 114, 0, 0.2)',
        'glow-blue': '0 0 20px rgba(0, 115, 230, 0.6)',
        'glow-purple': '0 0 20px rgba(124, 0, 230, 0.6)',
        'glow-orange': '0 0 20px rgba(255, 114, 0, 0.6)',
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'gradient': 'gradient 8s ease infinite',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 20px rgba(0, 115, 230, 0.4)' },
          '50%': { opacity: '0.8', boxShadow: '0 0 40px rgba(124, 0, 230, 0.6)' },
        },
        'gradient': {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
      },
    },
  },
  plugins: [],
}


