import { useCallback, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Bot, Loader2, Sparkles, X } from 'lucide-react';
import * as agentApi from '../lib/agentSpaceApi';
import { cn } from '../lib/utils';

export function surfaceFromPathname(pathname: string): string {
    if (pathname.startsWith('/chat')) return 'chat';
    if (pathname.startsWith('/builder')) return 'builder';
    if (pathname.startsWith('/self-code')) return 'self-code';
    if (pathname.startsWith('/automation')) return 'automation';
    if (pathname.startsWith('/agents')) return 'agents';
    if (pathname.startsWith('/agent-studio')) return 'agent-studio';
    return 'general';
}

type PlannedAgent = { id: string; role: string; depends_on: string[]; description: string };

/**
 * Global “cross-surface assist”: the app plans ephemeral specialist agents, streams a joint answer,
 * or starts a real Agent Space run—available from any primary tab.
 */
export function AppAssistDock({ hidden }: { hidden?: boolean }) {
    const location = useLocation();
    const [panelOpen, setPanelOpen] = useState(false);
    const [question, setQuestion] = useState('');
    const [context, setContext] = useState('');
    const [answer, setAnswer] = useState('');
    const [plannedAgents, setPlannedAgents] = useState<PlannedAgent[]>([]);
    const [delegateObjective, setDelegateObjective] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [spawnNotice, setSpawnNotice] = useState('');
    const abortRef = useRef<AbortController | null>(null);

    const surface = surfaceFromPathname(location.pathname);

    const stopStream = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = null;
    }, []);

    const runAnalyze = useCallback(async () => {
        const q = question.trim();
        if (!q || busy) return;
        setError('');
        setSpawnNotice('');
        setAnswer('');
        setPlannedAgents([]);
        setDelegateObjective('');
        stopStream();
        const ac = new AbortController();
        abortRef.current = ac;
        setBusy(true);
        try {
            await agentApi.streamCrossSurfaceAssist(
                { question: q, surface, context: context.trim() },
                {
                    signal: ac.signal,
                    onEvent: (ev) => {
                        if (ev.type === 'meta') {
                            setPlannedAgents(ev.agents);
                            setDelegateObjective(ev.delegate_objective);
                        }
                        if (ev.type === 'chunk') {
                            setAnswer((prev) => prev + ev.text);
                        }
                        if (ev.type === 'error') {
                            setError(ev.message);
                        }
                    },
                },
            );
        } catch (e) {
            if ((e as Error).name === 'AbortError') return;
            setError(e instanceof Error ? e.message : 'Assist stream failed.');
        } finally {
            setBusy(false);
            abortRef.current = null;
        }
    }, [busy, context, question, stopStream, surface]);

    const runSpawn = useCallback(async () => {
        const q = question.trim();
        if (!q || busy) return;
        setError('');
        setSpawnNotice('');
        stopStream();
        setBusy(true);
        try {
            const res = await agentApi.spawnAssistRun({
                question: q,
                surface,
                context: context.trim(),
                autonomous: true,
            });
            setSpawnNotice(`Run started: ${res.run.id} (${res.run.status}).`);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not start assist run.');
        } finally {
            setBusy(false);
        }
    }, [busy, context, question, stopStream, surface]);

    if (hidden) {
        return null;
    }

    return (
        <>
            <button
                type="button"
                onClick={() => {
                    setPanelOpen((o) => !o);
                    if (panelOpen) stopStream();
                }}
                className={cn(
                    'fixed z-[60] flex items-center gap-2 rounded-full border border-accent/35 bg-surface-1 px-3 py-2 text-xs font-semibold text-text-primary shadow-lg transition-colors',
                    'hover:border-accent/50 hover:bg-surface-2',
                    'bottom-[max(1rem,calc(env(safe-area-inset-bottom,0px)+4.5rem))] right-[max(0.75rem,env(safe-area-inset-right,0px))]',
                    'md:bottom-6 md:right-6',
                )}
                title="Cross-surface assist: app-planned agents for this tab"
                aria-expanded={panelOpen}
                aria-label={panelOpen ? 'Close assist panel' : 'Open assist panel'}
            >
                <Sparkles className="h-4 w-4 text-accent" aria-hidden />
                <span className="hidden sm:inline">Assist</span>
            </button>

            {panelOpen && (
                <div
                    className="fixed inset-0 z-[59] bg-black/40 md:bg-black/25"
                    role="presentation"
                    onClick={() => {
                        setPanelOpen(false);
                        stopStream();
                    }}
                />
            )}

            {panelOpen && (
                <div
                    className={cn(
                        'fixed z-[60] flex max-h-[min(92vh,720px)] w-[min(100vw-1.5rem,420px)] flex-col overflow-hidden rounded-xl border border-surface-5 bg-surface-1 shadow-2xl',
                        'bottom-[max(5.25rem,calc(env(safe-area-inset-bottom,0px)+5.25rem))] right-[max(0.75rem,env(safe-area-inset-right,0px))]',
                        'md:bottom-24 md:right-6 md:max-h-[min(85vh,640px)]',
                    )}
                    role="dialog"
                    aria-labelledby="app-assist-title"
                >
                    <div className="flex items-start justify-between gap-2 border-b border-surface-5 px-3 py-2.5">
                        <div className="min-w-0">
                            <h2 id="app-assist-title" className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                                <Bot className="h-4 w-4 shrink-0 text-accent" aria-hidden />
                                Cross-surface assist
                            </h2>
                            <p className="mt-0.5 text-[11px] text-text-muted">
                                Surface: <span className="font-mono text-text-secondary">{surface}</span> · ephemeral agents + optional run
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={() => {
                                setPanelOpen(false);
                                stopStream();
                            }}
                            className="rounded-md p-1.5 text-text-muted hover:bg-surface-3 hover:text-text-primary"
                            aria-label="Close"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    </div>

                    <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-2">
                        <label className="block text-[11px] font-medium text-text-muted" htmlFor="assist-question">
                            Question
                        </label>
                        <textarea
                            id="assist-question"
                            rows={3}
                            value={question}
                            onChange={(e) => setQuestion(e.target.value)}
                            placeholder="Ask anything—analysis uses agents tailored to this tab."
                            className="w-full resize-y rounded-lg border border-surface-5 bg-surface-0 px-2.5 py-2 text-sm text-text-primary outline-none placeholder:text-text-muted focus:border-accent/50"
                        />
                        <details className="text-[11px] text-text-muted">
                            <summary className="cursor-pointer select-none font-medium hover:text-text-secondary">Optional context</summary>
                            <textarea
                                rows={2}
                                value={context}
                                onChange={(e) => setContext(e.target.value)}
                                placeholder="Paste logs, file paths, error text…"
                                className="mt-1.5 w-full resize-y rounded-lg border border-surface-5 bg-surface-0 px-2.5 py-2 text-xs text-text-primary outline-none focus:border-accent/50"
                            />
                        </details>

                        {plannedAgents.length > 0 && (
                            <div className="rounded-lg border border-surface-5 bg-surface-0/80 p-2">
                                <p className="text-[10px] font-medium uppercase tracking-wide text-text-muted">Planned agents</p>
                                <ul className="mt-1.5 space-y-1 text-[11px] text-text-secondary">
                                    {plannedAgents.map((a) => (
                                        <li key={a.id}>
                                            <span className="font-mono text-accent/90">{a.id}</span>
                                            <span className="text-text-muted"> ({a.role})</span>
                                            {a.description ? <span> — {a.description}</span> : null}
                                        </li>
                                    ))}
                                </ul>
                                {delegateObjective ? (
                                    <p className="mt-2 border-t border-surface-5 pt-2 text-[11px] text-text-muted">
                                        <span className="font-medium text-text-secondary">Delegate line: </span>
                                        {delegateObjective}
                                    </p>
                                ) : null}
                            </div>
                        )}

                        {error ? <p className="rounded-md border border-accent-red/30 bg-accent-red/10 px-2 py-1.5 text-[11px] text-accent-red">{error}</p> : null}
                        {spawnNotice ? (
                            <p className="rounded-md border border-accent-green/30 bg-accent-green/10 px-2 py-1.5 text-[11px] text-accent-green">
                                {spawnNotice}{' '}
                                <Link to="/automation" className="font-medium underline hover:text-text-primary">
                                    Automation
                                </Link>
                            </p>
                        ) : null}

                        <div>
                            <p className="text-[10px] font-medium uppercase tracking-wide text-text-muted">Answer</p>
                            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-surface-5 bg-surface-0 p-2 font-sans text-[12px] leading-relaxed text-text-secondary">
                                {answer || (busy ? '…' : 'Run “Stream answer” to generate.')}
                            </pre>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-2 border-t border-surface-5 px-3 py-2.5">
                        <button
                            type="button"
                            onClick={() => runAnalyze().catch(() => undefined)}
                            disabled={busy || !question.trim()}
                            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-accent/90 disabled:opacity-50 min-[400px]:flex-none"
                        >
                            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
                            Stream answer
                        </button>
                        <button
                            type="button"
                            onClick={() => runSpawn().catch(() => undefined)}
                            disabled={busy || !question.trim()}
                            className="rounded-lg border border-surface-5 px-3 py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary disabled:opacity-50"
                        >
                            Spawn agent run
                        </button>
                        <button
                            type="button"
                            onClick={stopStream}
                            disabled={!busy}
                            className="rounded-lg border border-surface-5 px-3 py-2 text-xs text-text-muted hover:bg-surface-3 disabled:opacity-40"
                        >
                            Stop
                        </button>
                    </div>
                </div>
            )}
        </>
    );
}
