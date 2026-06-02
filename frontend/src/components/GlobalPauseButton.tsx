import { useCallback, useEffect, useState } from 'react';
import { Pause, Play, Loader2 } from 'lucide-react';
import * as agentApi from '../lib/agentSpaceApi';
import type { AgentActivity } from '../lib/agentSpaceApi';
import { cn } from '../lib/utils';

interface Props {
    /** `inline` sits in the desktop top bar; `floating` is a fixed pill for mobile. */
    variant?: 'inline' | 'floating';
}

type Phase = 'paused' | 'working' | 'loaded' | 'idle';

function derivePhase(a: AgentActivity | null): Phase {
    if (!a) return 'idle';
    if (!a.power_enabled) return 'paused';
    if (a.active_runs > 0) return 'working';
    if (a.model_loaded) return 'loaded';
    return 'idle';
}

const PHASE_META: Record<Phase, { word: string; dot: string; title: string }> = {
    paused: { word: 'Paused', dot: 'bg-accent-red', title: 'Generation paused — GPU stopped. Click to resume.' },
    working: { word: 'Working', dot: 'bg-accent-green animate-pulse', title: 'A job is actively running.' },
    loaded: { word: 'Model loaded', dot: 'bg-accent-amber', title: 'Idle, but a model is still in VRAM (auto-frees shortly).' },
    idle: { word: 'Idle', dot: 'bg-text-muted', title: 'GPU idle — no model loaded. Nothing running.' },
};

/**
 * Global generation pause + live thermal-safety status. Toggling power OFF trips
 * the backend kill-switch (models/ollama_client) which aborts every in-flight
 * Ollama generation within ~0.5s, so the GPU stops decoding — the stop the user
 * can hit from anywhere. The status word lets them confirm at a glance that
 * Ollama isn't "running on nothing." Polls so laptop + phone stay in sync.
 */
export default function GlobalPauseButton({ variant = 'inline' }: Props) {
    const [activity, setActivity] = useState<AgentActivity | null>(null);
    const [busy, setBusy] = useState(false);

    const poll = useCallback(async () => {
        try {
            setActivity(await agentApi.getActivity());
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
        if (busy || activity === null) return;
        const next = !activity.power_enabled;
        setBusy(true);
        setActivity({ ...activity, power_enabled: next }); // optimistic
        try {
            const state = await agentApi.setPowerState(next);
            setActivity((prev) => (prev ? { ...prev, power_enabled: Boolean(state?.enabled ?? next) } : prev));
        } catch {
            setActivity((prev) => (prev ? { ...prev, power_enabled: !next } : prev));
        } finally {
            setBusy(false);
            void poll();
        }
    }, [busy, activity, poll]);

    if (activity === null) return null;

    const phase = derivePhase(activity);
    const meta = PHASE_META[phase];
    const paused = phase === 'paused';
    const ActionIcon = busy ? Loader2 : paused ? Play : Pause;
    const actionLabel = paused ? 'Resume AI generation' : 'Pause AI generation';

    if (variant === 'floating') {
        return (
            <button
                type="button"
                onClick={toggle}
                disabled={busy}
                aria-label={actionLabel}
                aria-pressed={paused}
                title={meta.title}
                className={cn(
                    'fixed right-3 top-3 z-[60] flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold shadow-elevation-2 backdrop-blur transition-colors md:hidden',
                    paused
                        ? 'animate-pulse-soft border-accent-red/50 bg-accent-red/20 text-accent-red'
                        : 'border-surface-4 bg-surface-2/90 text-text-secondary',
                )}
                style={{ top: 'calc(env(safe-area-inset-top, 0px) + 0.75rem)' }}
            >
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', meta.dot)} aria-hidden />
                <span>{meta.word}</span>
                <span className="mx-0.5 h-3 w-px bg-current opacity-20" aria-hidden />
                <ActionIcon className={cn('h-4 w-4', busy && 'animate-spin')} aria-hidden />
                {paused ? 'Resume' : 'Pause'}
            </button>
        );
    }

    return (
        <div className="flex items-center gap-1.5">
            <span
                className="hidden items-center gap-1.5 rounded-btn px-1.5 py-1 text-[11px] text-text-muted lg:inline-flex"
                title={meta.title}
            >
                <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} aria-hidden />
                {meta.word}
            </span>
            <button
                type="button"
                onClick={toggle}
                disabled={busy}
                aria-label={actionLabel}
                aria-pressed={paused}
                title={paused ? 'Generation paused — click to resume' : 'Stop all generation (thermal safety)'}
                className={cn(
                    'flex items-center gap-1.5 rounded-btn px-2.5 py-1.5 text-xs font-medium transition-colors duration-150',
                    paused
                        ? 'border border-accent-red/40 bg-accent-red/10 text-accent-red hover:bg-accent-red/20'
                        : 'text-text-muted hover:bg-surface-3 hover:text-text-secondary',
                )}
            >
                <ActionIcon className={cn('h-3.5 w-3.5', busy && 'animate-spin')} aria-hidden />
                {paused ? 'Resume' : 'Pause'}
            </button>
        </div>
    );
}
