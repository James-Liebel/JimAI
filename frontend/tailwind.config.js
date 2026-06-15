/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
    theme: {
        extend: {
            colors: {
                // Warm-neutral charcoal ramp. Low chroma (R/G/B within a few points)
                // so it reads as a sophisticated warm grey, never brown/muddy.
                surface: {
                    0: '#1B1A18',
                    1: '#222120',
                    2: '#2A2826',
                    3: '#34322F',
                    4: '#3D3A37',
                    5: '#282624',
                },
                accent: {
                    DEFAULT: '#C96442',
                    hover: '#D4785A',
                    dim: 'rgba(201,100,66,0.12)',
                    // `accent-1` is the primary-action alias used across action buttons.
                    1: '#C96442',
                    // Hue aliases kept for existing usages — warmed to sit in the clay palette.
                    blue: '#6E86B8',
                    green: '#7BA05B',
                    amber: '#D9A441',
                    red: '#C0584B',
                    purple: '#A07CB0',
                },
                // Semantic status palette (success/warning/error) used by stat tiles,
                // verdict badges, and audit rows — warmed to match the clay accent.
                status: {
                    success: '#7BA05B',
                    warning: '#D9A441',
                    error: '#C0584B',
                },
                text: {
                    primary: '#F3F1EC',
                    secondary: '#B6B2AB',
                    muted: '#837F78',
                },
            },
            fontFamily: {
                sans: ['"Inter"', '-apple-system', '"Segoe UI"', 'sans-serif'],
                serif: ['"Newsreader"', 'Georgia', 'Cambria', 'serif'],
                mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
            },
            fontSize: {
                base: '15px',
            },
            lineHeight: {
                normal: '1.6',
            },
            borderRadius: {
                card: '10px',
                btn: '8px',
                badge: '6px',
                panel: '14px',
            },
            // Dark-theme elevation: shadows stay deep to read against warm near-black
            // surfaces, but softer than before so cards feel layered, not boxed-in.
            boxShadow: {
                'elevation-1': '0 1px 2px 0 rgba(0, 0, 0, 0.40)',
                'elevation-2': '0 4px 14px -3px rgba(0, 0, 0, 0.50)',
                'elevation-3': '0 16px 44px -8px rgba(0, 0, 0, 0.62)',
                'focus-ring': '0 0 0 2px rgba(201, 100, 66, 0.45)',
            },
            transitionTimingFunction: {
                'out-soft': 'cubic-bezier(0.22, 1, 0.36, 1)',
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
