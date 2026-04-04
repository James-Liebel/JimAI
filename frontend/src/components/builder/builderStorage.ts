const K = {
    sidebar: 'jimai_builder_sidebar_width_v1',
    right: 'jimai_builder_right_width_v1',
    bottom: 'jimai_builder_bottom_height_v1',
    minimalChrome: 'jimai_builder_minimal_chrome_v1',
} as const;

function clamp(n: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, n));
}

function readNum(key: string, fallback: number): number {
    if (typeof window === 'undefined') return fallback;
    try {
        const v = Number(window.localStorage.getItem(key));
        return Number.isFinite(v) ? v : fallback;
    } catch {
        return fallback;
    }
}

function readBool(key: string, fallback: boolean): boolean {
    if (typeof window === 'undefined') return fallback;
    try {
        const v = window.localStorage.getItem(key);
        if (v === '1' || v === 'true') return true;
        if (v === '0' || v === 'false') return false;
        return fallback;
    } catch {
        return fallback;
    }
}

export function loadBuilderLayout(): { sidebarWidth: number; rightWidth: number; bottomHeight: number } {
    return {
        sidebarWidth: clamp(readNum(K.sidebar, 260), 200, 520),
        rightWidth: clamp(readNum(K.right, 360), 260, 720),
        bottomHeight: clamp(readNum(K.bottom, 220), 100, 600),
    };
}

export function persistBuilderLayout(partial: Partial<{ sidebarWidth: number; rightWidth: number; bottomHeight: number }>): void {
    if (typeof window === 'undefined') return;
    try {
        if (partial.sidebarWidth != null) window.localStorage.setItem(K.sidebar, String(Math.round(partial.sidebarWidth)));
        if (partial.rightWidth != null) window.localStorage.setItem(K.right, String(Math.round(partial.rightWidth)));
        if (partial.bottomHeight != null) window.localStorage.setItem(K.bottom, String(Math.round(partial.bottomHeight)));
    } catch {
        // ignore quota / private mode
    }
}

export function loadMinimalChrome(): boolean {
    return readBool(K.minimalChrome, false);
}

export function persistMinimalChrome(value: boolean): void {
    if (typeof window === 'undefined') return;
    try {
        window.localStorage.setItem(K.minimalChrome, value ? '1' : '0');
    } catch {
        // ignore
    }
}
