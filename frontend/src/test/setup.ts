import '@testing-library/jest-dom/vitest';

// jsdom doesn't implement matchMedia; provide a no-op stub so components that use
// useMediaQuery (e.g. MessageBubble, AppLayout) render in tests instead of throwing.
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
    window.matchMedia = ((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
}
