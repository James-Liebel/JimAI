/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
    theme: {
        extend: {
            colors: {
                surface: {
                    0: '#0A0A0B',
                    1: '#111113',
                    2: '#1A1A1E',
                    3: '#222228',
                    4: '#2A2A30',
                    5: '#1E1E24',
                },
                accent: {
                    DEFAULT: '#3B82F6',
                    hover: '#2563EB',
                    dim: 'rgba(59,130,246,0.12)',
                    blue: '#3B82F6',
                    green: '#22C55E',
                    amber: '#F59E0B',
                    red: '#EF4444',
                    purple: '#A855F7',
                },
                text: {
                    primary: '#F0F0F5',
                    secondary: '#8888A0',
                    muted: '#55556A',
                },
            },
            fontFamily: {
                sans: ['"Outfit"', '"Geist"', '"Manrope"', 'sans-serif'],
                mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
            },
            fontSize: {
                base: '14px',
            },
            lineHeight: {
                normal: '1.6',
            },
            borderRadius: {
                card: '6px',
                btn: '6px',
                badge: '4px',
                panel: '8px',
            },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'fade-in': 'fadeIn 0.2s ease-out',
                'slide-up': 'slideUp 0.2s ease-out',
                'pulse-soft': 'pulseSoft 3s ease-in-out infinite',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                slideUp: {
                    '0%': { opacity: '0', transform: 'translateY(6px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                pulseSoft: {
                    '0%': { opacity: '0.2' },
                    '50%': { opacity: '0.6' },
                    '100%': { opacity: '0.2' },
                },
            },
        },
    },
    plugins: [],
};
