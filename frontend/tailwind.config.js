/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
    theme: {
        extend: {
            colors: {
                // UChicago greystone ramp on a white page. Ordering is unchanged from
                // the dark theme — higher index still means "further from the page" —
                // so every existing bg-surface-N / border-surface-N usage still reads
                // correctly, it just runs light-to-dark instead of dark-to-light.
                surface: {
                    0: '#FFFFFF',
                    1: '#F7F6F5',
                    2: '#F1F0EE',
                    3: '#E8E7E4',
                    4: '#D3D1CE',
                    5: '#E6E4E1',
                },
                accent: {
                    DEFAULT: '#800000',
                    hover: '#660000',
                    dim: 'rgba(128,0,0,0.10)',
                    // `accent-1` is the primary-action alias used across action buttons.
                    1: '#800000',
                    // Pressed/active maroon, a step below the resting accent.
                    deep: '#5C0000',
                    // UChicago's expanded palette. On white these hold at published
                    // strength, unlike the dark theme where every one needed lifting.
                    // The exception is orange: #C16622 is only 4.05:1 here, so it is
                    // darkened one step to clear 4.5:1 as text on panels too.
                    blue: '#155F83',
                    green: '#58593F',
                    amber: '#A8561B',
                    red: '#8F3931',
                    purple: '#350E20',
                },
                // Semantic status palette (success/warning/error) used by stat tiles,
                // verdict badges, and audit rows — warmed to match the clay accent.
                status: {
                    success: '#58593F',
                    warning: '#A8561B',
                    error: '#8F3931',
                },
                text: {
                    primary: '#1A1918',
                    secondary: '#4D4B49',
                    muted: '#6B6A69',
                },
            },
            fontFamily: {
                // Gotham and Mercury are UChicago's brand faces but are proprietary;
                // Montserrat and Source Serif 4 are the closest self-hostable analogs.
                sans: ['"Montserrat"', '-apple-system', '"Segoe UI"', 'sans-serif'],
                serif: ['"Source Serif 4"', 'Georgia', 'Cambria', 'serif'],
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
            // Light-theme elevation: on white, a shadow at dark-theme opacity reads as
            // a smudge, so these drop to the alpha a paper-like surface needs.
            boxShadow: {
                'elevation-1': '0 1px 2px 0 rgba(26, 25, 24, 0.08)',
                'elevation-2': '0 4px 14px -3px rgba(26, 25, 24, 0.12)',
                'elevation-3': '0 16px 44px -8px rgba(26, 25, 24, 0.18)',
                'focus-ring': '0 0 0 2px rgba(128, 0, 0, 0.35)',
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
