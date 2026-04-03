function normalizeBase(value: string): string {
    return value.replace(/\/+$/, '');
}

function resolveBackendBase(): string {
    const envBase = String(import.meta.env.VITE_API_BASE || '').trim();
    if (envBase) return normalizeBase(envBase);
    if (typeof window === 'undefined') return 'http://127.0.0.1:8000';

    const protocol = window.location.protocol || 'http:';
    const host = String(window.location.hostname || '').trim();
    const port = String(window.location.port || '').trim();

    if ((protocol === 'http:' || protocol === 'https:') && port === '8000') {
        return '';
    }

    // Vite dev: use same-origin so /api and /health go through vite.config.mjs proxy to :8000
    // (works for localhost and LAN URLs like http://192.168.x.x:5173).
    if (import.meta.env.DEV) {
        return '';
    }

    const resolvedHost = host && host !== '0.0.0.0' ? host : '127.0.0.1';
    return `${protocol}//${resolvedHost}:8000`;
}

export const API_BASE = resolveBackendBase();

export function apiUrl(path: string): string {
    if (!path) return API_BASE || '';
    if (/^https?:\/\//i.test(path)) return path;
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${API_BASE}${normalizedPath}`;
}
