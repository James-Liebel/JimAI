import { useCallback, useEffect, useRef, useState } from 'react';
import { Pause, Play, Loader2 } from 'lucide-react';
import * as agentApi from '../lib/agentSpaceApi';
import { cn } from '../lib/utils';

interface Props {
    /** `inline` sits in the desktop top bar; `floating` is a fixed pill for mobile. */
    variant?: 'inline' | 'floating';
}

/**
 * Global generation pause. Toggling power OFF trips the backend kill-switch
 * (models/ollama_client) which aborts every in-flight Ollama generation within
 * ~0.5s, so the GPU stops decoding to a possibly-disconnected phone — the
 * thermal-safety stop the user can hit from anywhere. Polls so multiple clients
 * (laptop + phone) stay in sync.
 */
export default function GlobalPauseButton({ variant = 'inline' }: Props) {
    const [enabled, setEnabled] = useState<boolean | null>(null);
    const [busy, setBusy] = useState(false);
    const releaseGpuRef = useRef<boolean>(false);

    const poll = useCallback(async () => {
        try {
            const state = await agentApi.getPowerState();
            setEnabled(Boolean(state?.enabled ?? true));
            releaseGpuRef.current = Boolean(state?.release_gpu_on_off ?? false);
        } catch {
            /* leave last known state; transient backend hiccup */
        }
    }, []);

    useEffect(() => {
        void poll();
        const id = window.setInterval(poll, 4000);
        return () => window.clearInterval(id);
    }, [poll]);

    const toggle = useCallback(async () => {
        if (busy || enabled === null) return;
        const next = !enabled;
        setBusy(true);
        setEnabled(next); // optimistic
        try {
            const state = await agentApi.setPowerState(next, releaseGpuRef.current);
            setEnabled(Boolean(state?.enabled ?? next));
        } catch {
            setEnabled(!next); // revert on failure
        } finally {
            setBusy(false);
        }
    }, [busy, enabled]);

    if (enabled === null) return null;

    const paused = !enabled;
    const label = paused ? 'Paused — Resume AI' : 'Pause AI';
    const Icon = busy ? Loader2 : paused ? Play : Pause;

    if (variant === 'floating') {
        return (
            <button
                type="button"
                onClick={toggle}
                disabled={busy}
                aria-label={label}
                aria-pressed={paused}
                className={cn(
                    'fixed right-3 top-3 z-[60] flex items-center gap-1.5 rounded-full border px-3 py-2 text-xs font-semibold shadow-elevation-2 backdrop-blur transition-colors md:hidden',
                    paused
                        ? 'animate-pulse-soft border-accent-red/50 bg-accent-red/20 text-accent-red'
                        : 'border-surface-4 bg-surface-2/90 text-text-secondary',
                )}
                style={{ top: 'calc(env(safe-area-inset-top, 0px) + 0.75rem)' }}
            >
                <Icon className={cn('h-4 w-4', busy && 'animate-spin')} aria-hidden />
                {paused ? 'Resume' : 'Pause'}
            </button>
        );
    }

    return (
        <button
            type="button"
            onClick={toggle}
            disabled={busy}
            aria-label={label}
            aria-pressed={paused}
            title={paused ? 'Generation paused — click to resume' : 'Stop all generation (thermal safety)'}
            className={cn(
                'flex items-center gap-1.5 rounded-btn px-2.5 py-1.5 text-xs font-medium transition-colors duration-150',
                paused
                    ? 'border border-accent-red/40 bg-accent-red/10 text-accent-red hover:bg-accent-red/20'
                    : 'text-text-muted hover:bg-surface-3 hover:text-text-secondary',
            )}
        >
            <Icon className={cn('h-3.5 w-3.5', busy && 'animate-spin')} aria-hidden />
            {paused ? 'Resume' : 'Pause'}
        </button>
    );
}
