import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import { Button } from './ui/Button';

/**
 * Shows a tap-to-update button when the server is serving a newer build than the
 * one this tab booted from.
 *
 * The case this exists for is the phone: an installed PWA resumed from suspend
 * never re-fetches on its own, so a new build can sit on the server for days
 * while the home-screen app keeps rendering the bundle it started with.
 */

const POLL_INTERVAL_MS = 5 * 60 * 1000;

async function fetchDeployedBuildId(): Promise<string | null> {
    try {
        const res = await fetch('/build-id.json', { cache: 'no-store' });
        if (!res.ok) return null;
        const data = (await res.json()) as { id?: unknown };
        return typeof data.id === 'string' ? data.id : null;
    } catch {
        // Offline or dev server without the emitted file — nothing to report.
        return null;
    }
}

export function UpdateBanner() {
    const [isUpdateReady, setIsUpdateReady] = useState(false);
    const [isApplying, setIsApplying] = useState(false);

    useEffect(() => {
        let isCancelled = false;

        const check = async () => {
            const deployed = await fetchDeployedBuildId();
            if (isCancelled || !deployed) return;
            if (deployed !== __BUILD_ID__) setIsUpdateReady(true);
        };

        void check();
        const intervalId = window.setInterval(() => void check(), POLL_INTERVAL_MS);
        // Re-check on resume: for a suspended PWA this fires long before the timer would.
        const handleVisibility = () => {
            if (document.visibilityState === 'visible') void check();
        };
        document.addEventListener('visibilitychange', handleVisibility);

        return () => {
            isCancelled = true;
            window.clearInterval(intervalId);
            document.removeEventListener('visibilitychange', handleVisibility);
        };
    }, []);

    const handleUpdate = useCallback(async () => {
        setIsApplying(true);
        // Drop the service worker and its caches first — a plain reload can otherwise
        // be answered by the worker that is already holding the previous bundle.
        try {
            if ('serviceWorker' in navigator) {
                const registrations = await navigator.serviceWorker.getRegistrations();
                await Promise.all(registrations.map((registration) => registration.unregister()));
            }
            if ('caches' in window) {
                const keys = await caches.keys();
                await Promise.all(keys.map((key) => caches.delete(key)));
            }
        } catch (err) {
            console.warn('Update cleanup failed, reloading anyway:', err);
        }
        window.location.reload();
    }, []);

    if (!isUpdateReady) return null;

    return (
        <div
            className="pointer-events-none fixed inset-x-0 z-50 flex justify-center px-4"
            style={{ top: 'calc(env(safe-area-inset-top, 0px) + 10px)' }}
        >
            <Button
                variant="primary"
                size="md"
                disabled={isApplying}
                onClick={() => void handleUpdate()}
                className="pointer-events-auto rounded-full shadow-elevation-2 animate-fade-in"
            >
                <RefreshCw size={14} className={isApplying ? 'animate-spin' : undefined} />
                {isApplying ? 'Updating…' : 'Update available — tap to refresh'}
            </Button>
        </div>
    );
}
