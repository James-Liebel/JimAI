import { useState, useEffect, useCallback, useRef } from 'react';
import { GitPullRequest, MessageSquare, Settings } from 'lucide-react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { cn } from '../lib/utils';
import { useMediaQuery } from '../hooks/useMediaQuery';
import MobileNav from './MobileNav';
import type { SpeedMode } from '../lib/types';
import * as api from '../lib/api';
import * as agentApi from '../lib/agentSpaceApi';
import { apiUrl } from '../lib/backendBase';

const NAV_ITEMS = [
    { to: '/chat', label: 'Chat' },
    { to: '/builder', label: 'Builder' },
    { to: '/agents', label: 'Agents' },
    { to: '/automation', label: 'Automation' },
    { to: '/system', label: 'System' },
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
        const checkHealth = async () => {
            try {
                const health = await api.getHealth();
                ollamaHealthFailuresRef.current = 0;
                setOllamaHealth({
                    checked: true,
                    ok: Boolean(health.services?.ollama),
                    url: String(health.ollama_url || 'http://localhost:11434'),
                    backendReachable: true,
                });
            } catch {
                ollamaHealthFailuresRef.current += 1;
                if (ollamaHealthFailuresRef.current < 3) return;
                setOllamaHealth((current) => ({
                    checked: true,
                    ok: false,
                    url: current.url || 'http://localhost:11434',
                    backendReachable: false,
                }));
            }
        };
        checkHealth().catch(() => undefined);
        const id = window.setInterval(() => checkHealth().catch(() => undefined), 5000);
        return () => window.clearInterval(id);
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
            isDeep && 'ring-1 ring-accent/30',
        )}>
            {!isMobile && (
                <nav className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-surface-3 bg-surface-1 gap-3">
                    <div className="flex items-center gap-3">
                        <div className="w-7 h-7 rounded-md bg-gradient-to-br from-accent to-accent-blue flex items-center justify-center text-black font-bold text-xs animate-pulse-slow">
                            jA
                        </div>
                        <span className="font-semibold text-sm text-text-primary tracking-tight">
                            jimAI
                        </span>
                    </div>
                    <div className="flex items-center gap-1 bg-surface-0 rounded-md p-0.5 overflow-auto">
                        {NAV_ITEMS.map(({ to, label }) => (
                            <NavLink
                                key={to}
                                to={to}
                                className={({ isActive }) =>
                                    cn(
                                        'px-3 py-1.5 rounded text-xs font-medium transition-all',
                                        isActive
                                            ? 'bg-surface-3 text-text-primary'
                                            : 'text-text-secondary hover:text-text-primary hover:bg-surface-2',
                                    )
                                }
                            >
                                {label}
                            </NavLink>
                        ))}
                    </div>
                    <div className="flex items-center gap-2">
                        <NavLink
                            to="/workflow"
                            className={({ isActive }) =>
                                cn(
                                    'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all border',
                                    isActive
                                        ? 'bg-surface-3 text-text-primary border-surface-4'
                                        : 'text-text-secondary border-surface-3 hover:text-text-primary hover:bg-surface-2',
                                )
                            }
                        >
                            <GitPullRequest size={14} />
                            Review
                        </NavLink>
                        <NavLink
                            to="/settings"
                            title="Settings"
                            className={({ isActive }) =>
                                cn(
                                    'p-2 rounded border transition-all',
                                    isActive
                                        ? 'bg-surface-3 text-text-primary border-surface-4'
                                        : 'text-text-secondary border-surface-3 hover:text-text-primary hover:bg-surface-2',
                                )
                            }
                        >
                            <Settings size={14} />
                        </NavLink>
                    </div>
                </nav>
            )}

            {deepWarning && (
                <div className="flex-shrink-0 px-4 py-1.5 bg-accent/10 border-b border-accent/25 text-accent text-xs text-center animate-fade-in">
                    {deepWarning}
                    <button onClick={() => setDeepWarning('')} className="ml-3 text-accent hover:text-text-primary">✕</button>
                </div>
            )}

            {ollamaHealth.checked && !ollamaHealth.ok && (
                <div className="flex-shrink-0 border-b border-accent-red/30 bg-accent-red/10 px-4 py-2 text-xs text-accent-red">
                    {ollamaHealth.backendReachable ? (
                        <>
                            Ollama is not reachable at {ollamaHealth.url}. Start it with <span className="font-mono">ollama serve</span> and confirm your Ollama URL in Settings.
                        </>
                    ) : (
                        <>
                            Backend health is not reachable at <span className="font-mono">http://localhost:8000</span>. Start the backend first; Ollama may still be running normally.
                        </>
                    )}
                </div>
            )}

            <div className={`flex-1 overflow-hidden ${isMobile ? 'pb-[calc(52px+env(safe-area-inset-bottom,0px))]' : ''}`}>
                <Outlet context={{ speedMode, onSpeedModeChange: handleSpeedModeChange }} />
            </div>
            {isMobile && location.pathname !== '/chat' && (
                <button
                    type="button"
                    onClick={() => navigate('/chat')}
                    className="fixed right-4 z-50 flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-xs font-semibold text-surface-0 shadow-lg md:hidden"
                    style={{ bottom: 'calc(64px + env(safe-area-inset-bottom, 0px))' }}
                    aria-label="Open chat"
                >
                    <MessageSquare size={16} />
                    Text
                </button>
            )}
            {isMobile && <MobileNav />}
        </div>
    );
}
