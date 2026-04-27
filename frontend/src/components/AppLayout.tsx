import { useState, useEffect, useCallback, useRef } from 'react';
import { GitPullRequest, Settings } from 'lucide-react';
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { cn } from '../lib/utils';
import { useMediaQuery } from '../hooks/useMediaQuery';
import MobileNav from './MobileNav';
import { AppAssistDock } from './AppAssistDock';
import CommandPalette from './CommandPalette';
import type { SpeedMode } from '../lib/types';
import * as api from '../lib/api';
import * as agentApi from '../lib/agentSpaceApi';
import { API_BASE, apiUrl } from '../lib/backendBase';

const NAV_ITEMS = [
    { to: '/chat', label: 'Chat' },
    { to: '/atlas', label: 'Atlas' },
    { to: '/builder', label: 'Builder' },
    { to: '/agents', label: 'Agents' },
    { to: '/self-code', label: 'SelfCode' },
];

const TERMINAL_RUN_EVENTS = new Set(['run.completed', 'run.failed', 'run.stopped']);

function normalizeTimestamp(value: unknown): number {
    const raw = Number(value || 0);
    if (!Number.isFinite(raw) || raw <= 0) return 0;
    return raw > 1e12 ? raw / 1000 : raw;
}

function formatDuration(seconds: number): string {
    if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s`;
    const whole = Math.round(seconds);
    const mins = Math.floor(whole / 60);
    const secs = whole % 60;
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

async function showTaskNotification(title: string, body: string, runId: string): Promise<void> {
    if (typeof window === 'undefined' || !('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;
    const options: NotificationOptions = {
        body,
        tag: `agent-space-run-${runId}`,
        icon: '/icons/icon-192.png',
        badge: '/icons/icon-192.png',
    };
    if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        if (registration) {
            await registration.showNotification(title, options);
            return;
        }
    }
    new Notification(title, options);
}

export default function AppLayout() {
    const isMobile = useMediaQuery('(max-width: 768px)');
    const navigate = useNavigate();
    const location = useLocation();
    const [searchParams] = useSearchParams();
    const builderFullChrome = location.pathname === '/builder' && searchParams.get('full') === '1';
    const isAtlasTab = location.pathname === '/browser';
    const [speedMode, setSpeedMode] = useState<SpeedMode>('balanced');
    const [deepWarning, setDeepWarning] = useState('');
    const [phoneNotificationsEnabled, setPhoneNotificationsEnabled] = useState(false);
    const [phoneNotificationMinSeconds, setPhoneNotificationMinSeconds] = useState(120);
    const [phoneNotificationsOnFailure, setPhoneNotificationsOnFailure] = useState(true);
    const [ollamaHealth, setOllamaHealth] = useState<{ checked: boolean; ok: boolean; url: string; backendReachable: boolean }>({
        checked: false,
        ok: true,
        url: 'http://localhost:11434',
        backendReachable: true,
    });
    const notifiedRunIdsRef = useRef<Set<string>>(new Set());
    const runStartTimesRef = useRef<Map<string, number>>(new Map());
    const ollamaHealthFailuresRef = useRef(0);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const appInstanceIdRef = useRef('');
    const appInstanceHeartbeatRef = useRef<number | null>(null);
    const appInstanceClosedRef = useRef(false);

    useEffect(() => {
        api.getSpeedMode()
            .then((res) => setSpeedMode(res.mode as SpeedMode))
            .catch(() => {});
    }, []);

    useEffect(() => {
        const storageKey = 'jimai_app_instance_id';
        const randomId = (() => {
            try {
                if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
                    return crypto.randomUUID();
                }
            } catch {
                // fallback below
            }
            return `instance-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
        })();
        const existing = window.sessionStorage.getItem(storageKey) || '';
        const instanceId = (existing || randomId).trim();
        window.sessionStorage.setItem(storageKey, instanceId);
        appInstanceIdRef.current = instanceId;
        appInstanceClosedRef.current = false;

        const metadata = {
            route: location.pathname,
            user_agent: navigator.userAgent,
            viewport: `${window.innerWidth}x${window.innerHeight}`,
        };

        agentApi
            .registerAppInstance({ instance_id: instanceId, client: 'ui', metadata })
            .catch(() => {});

        appInstanceHeartbeatRef.current = window.setInterval(() => {
            const id = appInstanceIdRef.current;
            if (!id) return;
            agentApi
                .heartbeatAppInstance({ instance_id: id, client: 'ui', metadata })
                .catch(() => {});
        }, 15000);

        const notifyClosed = (reason: string) => {
            if (appInstanceClosedRef.current) return;
            const id = appInstanceIdRef.current;
            if (!id) return;
            appInstanceClosedRef.current = true;
            const payload = JSON.stringify({ instance_id: id, reason });
            fetch(apiUrl('/api/agent-space/instances/unregister'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-JimAI-CSRF': '1',
                },
                body: payload,
                keepalive: true,
            }).catch(() => {});
        };

        const onPageHide = () => notifyClosed('pagehide');
        const onBeforeUnload = () => notifyClosed('beforeunload');
        window.addEventListener('pagehide', onPageHide);
        window.addEventListener('beforeunload', onBeforeUnload);

        return () => {
            if (appInstanceHeartbeatRef.current) {
                window.clearInterval(appInstanceHeartbeatRef.current);
                appInstanceHeartbeatRef.current = null;
            }
            window.removeEventListener('pagehide', onPageHide);
            window.removeEventListener('beforeunload', onBeforeUnload);
        };
    }, []);

    const loadNotificationSettings = useCallback(() => {
        agentApi.getSettings()
            .then((cfg) => {
                setPhoneNotificationsEnabled(Boolean(cfg.phone_notifications_enabled));
                setPhoneNotificationMinSeconds(Math.max(0, Number(cfg.phone_notification_min_seconds ?? 120)));
                setPhoneNotificationsOnFailure(Boolean(cfg.phone_notifications_on_failure ?? true));
            })
            .catch(() => {});
    }, []);

    useEffect(() => {
        loadNotificationSettings();
        const id = window.setInterval(loadNotificationSettings, 15000);
        return () => window.clearInterval(id);
    }, [loadNotificationSettings]);

    useEffect(() => {
        let timer: number | null = null;
        let cancelled = false;

        const checkHealth = async (): Promise<boolean> => {
            try {
                const health = await api.getHealth();
                ollamaHealthFailuresRef.current = 0;
                setOllamaHealth({
                    checked: true,
                    ok: Boolean(health.services?.ollama),
                    url: String(health.ollama_url || 'http://localhost:11434'),
                    backendReachable: true,
                });
                return true;
            } catch {
                ollamaHealthFailuresRef.current += 1;
                if (ollamaHealthFailuresRef.current >= 3) {
                    setOllamaHealth((current) => ({
                        checked: true,
                        ok: false,
                        url: current.url || 'http://localhost:11434',
                        backendReachable: false,
                    }));
                }
                return false;
            }
        };

        const schedule = (delayMs: number) => {
            if (cancelled) return;
            timer = window.setTimeout(async () => {
                const ok = await checkHealth();
                // Healthy: poll every 5s. Failing: back off 5 → 10 → 20 → 30s (cap).
                const failures = ollamaHealthFailuresRef.current;
                const next = ok ? 5000 : Math.min(30000, 5000 * Math.pow(2, Math.max(0, failures - 1)));
                schedule(next);
            }, delayMs);
        };

        schedule(0);
        return () => {
            cancelled = true;
            if (timer !== null) window.clearTimeout(timer);
        };
    }, []);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
                e.preventDefault();
                setPaletteOpen((o) => !o);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    useEffect(() => {
        // Mobile users should land on chat-first texting UX.
        if (isMobile && location.pathname === '/') {
            navigate('/chat', { replace: true });
        }
    }, [isMobile, location.pathname, navigate]);

    useEffect(() => {
        if (!phoneNotificationsEnabled) return;
        if (typeof window === 'undefined' || !('Notification' in window)) return;

        const unsubscribe = agentApi.subscribeGlobalEvents(async (event) => {
            if (!event || !event.type) return;
            const runId = String(event.run_id || '');
            if (!runId) return;

            if (event.type === 'run.started') {
                const startedAt = normalizeTimestamp(event.timestamp);
                if (startedAt > 0) {
                    runStartTimesRef.current.set(runId, startedAt);
                }
                return;
            }

            if (!TERMINAL_RUN_EVENTS.has(event.type)) return;
            if (event.type !== 'run.completed' && !phoneNotificationsOnFailure) return;
            if (notifiedRunIdsRef.current.has(runId)) return;

            try {
                const run = await agentApi.getRun(runId);
                const startedAt = normalizeTimestamp(run.started_at ?? run.created_at ?? runStartTimesRef.current.get(runId));
                const endedAt = normalizeTimestamp(run.ended_at ?? event.timestamp ?? Date.now() / 1000);
                const durationSeconds = Math.max(0, endedAt - startedAt);
                if (durationSeconds < phoneNotificationMinSeconds) return;

                const objective = String(run.objective || 'Task');
                const status = String(run.status || 'completed');
                const title = status === 'completed'
                    ? 'jimAI task completed'
                    : status === 'failed'
                        ? 'jimAI task failed'
                        : 'jimAI task stopped';
                const body = `${objective.slice(0, 120)} (${formatDuration(durationSeconds)})`;
                await showTaskNotification(title, body, runId);
                notifiedRunIdsRef.current.add(runId);
                runStartTimesRef.current.delete(runId);
            } catch {
                // Ignore transient backend/network errors for notification sidecar logic.
            }
        });

        return () => unsubscribe();
    }, [phoneNotificationMinSeconds, phoneNotificationsEnabled, phoneNotificationsOnFailure]);

    const handleSpeedModeChange = useCallback(async (mode: SpeedMode) => {
        const prev = speedMode;
        setSpeedMode(mode);
        setDeepWarning('');
        try {
            const res = await api.setSpeedMode(mode);
            setSpeedMode(res.mode as SpeedMode);
            if (res.warning) setDeepWarning(res.warning);
        } catch {
            setSpeedMode(prev);
        }
    }, [speedMode]);

    const isDeep = speedMode === 'deep';

    return (
        <div className={cn(
            'h-full flex flex-col bg-surface-0 overflow-hidden font-sans text-text-primary',
            isDeep && 'ring-1 ring-inset ring-accent-amber/20',
        )}>
            {!isMobile && !builderFullChrome && (
                <nav className="flex h-12 shrink-0 items-center justify-between border-b border-surface-5 bg-surface-1 px-4 md:px-5">
                    {/* Logo + Assist trigger */}
                    <div className="flex shrink-0 items-center gap-3">
                        <div className="flex items-center gap-2.5">
                            <div className="flex h-6 w-6 items-center justify-center rounded-badge border border-accent/30 bg-accent/10 text-[10px] font-bold tracking-tight text-accent">
                                jA
                            </div>
                            <span className="text-sm font-semibold tracking-tight text-text-primary">jimAI</span>
                        </div>
                        <AppAssistDock hidden={builderFullChrome || isAtlasTab} />
                    </div>

                    {/* Center underline-style tabs */}
                    <div className="mx-4 flex h-full min-w-0 flex-1 items-stretch justify-center overflow-x-auto sm:max-w-[min(40rem,100%)]">
                        {NAV_ITEMS.map(({ to, label }) => (
                            <NavLink
                                key={to}
                                to={to}
                                className={({ isActive }) =>
                                    cn(
                                        'relative flex items-center px-3.5 text-xs font-medium tracking-wide transition-colors duration-150 md:px-4',
                                        'after:absolute after:inset-x-1 after:bottom-0 after:h-[2px] after:rounded-t-full after:transition-opacity after:duration-150',
                                        isActive
                                            ? 'text-text-primary after:bg-accent after:opacity-100'
                                            : 'text-text-muted hover:text-text-secondary after:bg-accent after:opacity-0',
                                    )
                                }
                            >
                                {label}
                            </NavLink>
                        ))}
                    </div>

                    {/* Right actions */}
                    <div className="flex shrink-0 items-center gap-1">
                        <NavLink
                            to="/workflow"
                            className={({ isActive }) =>
                                cn(
                                    'flex items-center gap-1.5 rounded-btn px-2.5 py-1.5 text-xs font-medium transition-colors duration-150',
                                    isActive
                                        ? 'bg-accent/10 text-accent'
                                        : 'text-text-muted hover:bg-surface-3 hover:text-text-secondary',
                                )
                            }
                        >
                            <GitPullRequest size={13} />
                            JimAI review
                        </NavLink>
                        <NavLink
                            to="/settings"
                            title="Settings"
                            className={({ isActive }) =>
                                cn(
                                    'rounded-btn p-2 transition-colors duration-150',
                                    isActive
                                        ? 'bg-accent/10 text-accent'
                                        : 'text-text-muted hover:bg-surface-3 hover:text-text-secondary',
                                )
                            }
                        >
                            <Settings size={14} />
                        </NavLink>
                    </div>
                </nav>
            )}

            {deepWarning && (
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-accent-amber/20 bg-accent-amber/8 px-4 py-2 text-xs text-accent-amber animate-fade-in">
                    <span className="min-w-0 flex-1 font-medium">{deepWarning}</span>
                    <button
                        type="button"
                        onClick={() => setDeepWarning('')}
                        className="shrink-0 rounded px-2 py-1 text-accent-amber/70 transition-colors hover:text-accent-amber"
                        aria-label="Dismiss warning"
                    >
                        Dismiss
                    </button>
                </div>
            )}

            {ollamaHealth.checked && !ollamaHealth.ok && (
                <div className="flex shrink-0 items-center gap-2 border-b border-accent-red/20 bg-accent-red/8 px-4 py-2 text-xs text-accent-red">
                    <span className="shrink-0 font-medium">Offline:</span>
                    {ollamaHealth.backendReachable ? (
                        <span>
                            Ollama not reachable at {ollamaHealth.url}. Run{' '}
                            <code className="font-mono text-accent-red/90">ollama serve</code> or update the URL in Settings.
                        </span>
                    ) : (
                        <span>
                            Backend unreachable
                            {API_BASE ? (
                                <> at <code className="font-mono">{API_BASE}</code></>
                            ) : (
                                <> (expects <code className="font-mono">http://localhost:8000</code>)</>
                            )}{' '}
                            — start the FastAPI backend first.
                        </span>
                    )}
                </div>
            )}

            <div className={`flex-1 min-h-0 overflow-hidden ${isMobile ? 'pb-[calc(52px+env(safe-area-inset-bottom,0px))]' : ''}`}>
                <main
                    id="main-content"
                    tabIndex={-1}
                    className="h-full min-h-0 overflow-hidden outline-none focus:outline-none"
                >
                    <Outlet context={{ speedMode, onSpeedModeChange: handleSpeedModeChange }} />
                </main>
            </div>
            {isMobile && <MobileNav />}
            <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        </div>
    );
}
