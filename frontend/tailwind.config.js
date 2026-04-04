/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
    theme: {
        extend: {
            colors: {
                /** Flat neutrals: depth mostly from borders, not many gray steps */
                surface: {
                    0: '#0a0a0a',
                    1: '#121212',
                    2: '#1a1a1a',
                    3: '#2a2a2a',
                    4: '#383838',
                },
                accent: {
                    DEFAULT: '#f5f5f5',
                    hover: '#ffffff',
                    dim: '#c8c8c8',
                    blue: '#ffffff',
                    green: '#ededed',
                    amber: '#d9d9d9',
                    red: '#f87979',
                    purple: '#f2f2f2',
                },
                text: {
                    primary: '#ffffff',
                    secondary: '#e3e3e3',
                    muted: '#b7b7b7',
                },
            },
            fontFamily: {
                sans: ['"Manrope"', '"Sora"', 'sans-serif'],
                mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
            },
            fontSize: {
                base: '14px',
            },
            lineHeight: {
                normal: '1.6',
            },
            borderRadius: {
                card: '0',
                btn: '0',
                badge: '0',
            },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'fade-in': 'fadeIn 0.3s ease-out',
                'slide-up': 'slideUp 0.3s ease-out',
                'orb-drift': 'orbDrift 18s ease-in-out infinite',
                'orb-drift-reverse': 'orbDriftReverse 22s ease-in-out infinite',
                'pulse-soft': 'pulseSoft 3s ease-in-out infinite',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                slideUp: {
                    '0%': { opacity: '0', transform: 'translateY(10px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                orbDrift: {
                    '0%': { transform: 'translate3d(-2%, -1%, 0) scale(1)' },
                    '50%': { transform: 'translate3d(8%, 5%, 0) scale(1.08)' },
                    '100%': { transform: 'translate3d(-2%, -1%, 0) scale(1)' },
                },
                orbDriftReverse: {
                    '0%': { transform: 'translate3d(3%, 2%, 0) scale(1)' },
                    '50%': { transform: 'translate3d(-7%, -6%, 0) scale(1.1)' },
                    '100%': { transform: 'translate3d(3%, 2%, 0) scale(1)' },
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
