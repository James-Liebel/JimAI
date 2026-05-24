// Warm a route's lazy chunk before the user clicks, so navigation feels instant.
// Specifiers must match the dynamic imports in main.tsx so Vite reuses the same chunk.
const ROUTE_IMPORTS: Record<string, () => Promise<unknown>> = {
    '/chat': () => import('../pages/Chat'),
    '/atlas': () => import('../pages/BrowserAtlas'),
    '/builder': () => import('../pages/Builder'),
    '/agents': () => import('../pages/Agents'),
    '/agent-studio': () => import('../pages/AgentStudio'),
    '/self-code': () => import('../pages/SelfCode'),
    '/autonomy': () => import('../pages/Autonomy'),
    '/security': () => import('../pages/Security'),
    '/workflow': () => import('../pages/WorkflowReview'),
    '/settings': () => import('../pages/Settings'),
    '/research': () => import('../pages/Research'),
    '/skills': () => import('../pages/Skills'),
    '/automation': () => import('../pages/Automation'),
    '/dashboard': () => import('../pages/Dashboard'),
    '/notebook': () => import('../pages/Notebook'),
    '/audit': () => import('../pages/SystemAudit'),
    '/browser': () => import('../pages/AgentBrowser'),
};

const prefetched = new Set<string>();

/** Idempotently preload a route's chunk. Safe to call repeatedly (e.g. on hover/focus). */
export function prefetchRoute(path: string): void {
    if (prefetched.has(path)) return;
    const load = ROUTE_IMPORTS[path];
    if (!load) return;
    prefetched.add(path);
    // Re-allow a retry if the chunk fails to load (e.g. transient network/offline).
    void load().catch(() => prefetched.delete(path));
}
