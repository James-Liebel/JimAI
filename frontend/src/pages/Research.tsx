import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import * as agentApi from '../lib/agentSpaceApi';

type StepState = 'pending' | 'running' | 'done' | 'skipped';

const STEP_ORDER: Array<{ key: string; label: string }> = [
    { key: 'query_rewrite', label: 'Rewriting query...' },
    { key: 'memory', label: 'Checking memory (Qdrant)...' },
    { key: 'search', label: 'Searching SearXNG · Bing · Google · DDG · Wikipedia...' },
    { key: 'read_pages', label: 'Reading top pages...' },
    { key: 'synthesis', label: 'Synthesizing answer...' },
];

const SUGGESTED_QUERIES = [
    'latest advances in transformer architecture 2025',
    'what is SMOTE oversampling technique',
    'SpaceX launches 2025',
    'best open source vector databases for local AI agents',
];

function statusGlyph(state: StepState): string {
    if (state === 'running') return '◎';
    if (state === 'done') return '✓';
    if (state === 'skipped') return '—';
    return '○';
}

function serviceBadgeClass(ok: boolean): string {
    return ok
        ? 'border-accent-green/40 text-accent-green bg-accent-green/10'
        : 'border-accent-red/40 text-accent-red bg-accent-red/10';
}

function normalizeScore(value?: number): number {
    if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
    if (value > 1) return Math.max(0, Math.min(1, value / 100));
    return Math.max(0, Math.min(1, value));
}

function sourceDomain(url?: string): string {
    if (!url) return '';
    try {
        return new URL(url).hostname.replace(/^www\./, '');
    } catch {
        return '';
    }
}

function confidenceLabel(score?: number): string {
    const normalized = normalizeScore(score);
    if (normalized >= 0.8) return 'high match';
    if (normalized >= 0.5) return 'medium match';
    if (normalized > 0) return 'low match';
    return 'unscored';
}

function queryNeedsFreshness(query: string): boolean {
    const lowered = query.toLowerCase();
    return ['latest', 'today', 'current', 'price', 'cost', '2025', '2026', 'news'].some((term) => lowered.includes(term));
}

export default function Research() {
    const [query, setQuery] = useState('');
    const [answer, setAnswer] = useState('');
    const [sources, setSources] = useState<agentApi.ResearchRunResult['sources']>([]);
    const [searching, setSearching] = useState(false);
    const [forceLive, setForceLive] = useState(false);
    const [error, setError] = useState('');
    const [timings, setTimings] = useState<Record<string, number>>({});
    const [services, setServices] = useState<Record<string, agentApi.ResearchServiceProbe>>({});
    const [memoryHit, setMemoryHit] = useState<{
        matchPercent: number;
        cachedAt: string;
        cachedAgeLabel: string;
    } | null>(null);
    const [rawMode, setRawMode] = useState(false);
    const [steps, setSteps] = useState<Record<string, StepState>>(() =>
        STEP_ORDER.reduce((acc, row) => ({ ...acc, [row.key]: 'pending' as StepState }), {}),
    );
    const cancelledRef = useRef(false);

    const offlineServices = useMemo(
        () => Object.values(services).filter((svc) => svc && svc.ok === false).map((svc) => svc.name),
        [services],
    );

    const activeStepLabel = useMemo(() => {
        const running = STEP_ORDER.find((s) => steps[s.key] === 'running');
        return running ? running.label : null;
    }, [steps]);

    const answerParagraphs = useMemo(
        () => answer.split(/\n\s*\n/).map((row) => row.trim()).filter(Boolean),
        [answer],
    );
    const compactSummary = answerParagraphs[0] || '';
    const compactSummaryLine = compactSummary.length > 260 ? `${compactSummary.slice(0, 257)}...` : compactSummary;
    const sourceCount = sources.length;
    const trustLabel = memoryHit
        ? 'Memory-backed'
        : rawMode
            ? 'Source-summary fallback'
            : sourceCount > 0
                ? 'Live source-backed'
                : 'No source backing yet';
    const rankedSources = useMemo(
        () => [...sources].sort((left, right) => normalizeScore((right as { score?: number }).score) - normalizeScore((left as { score?: number }).score)),
        [sources],
    );
    const freshnessNeeded = queryNeedsFreshness(query);

    useEffect(() => {
        let cancelled = false;
        agentApi
            .getResearchStatus()
            .then((data) => {
                if (!cancelled) setServices(data || {});
            })
            .catch(() => {
                // Keep UI usable even when status probe fails.
            });
        return () => {
            cancelled = true;
        };
    }, []);

    const resetRunState = () => {
        setAnswer('');
        setSources([]);
        setError('');
        setRawMode(false);
        setTimings({});
        setMemoryHit(null);
        setSteps(STEP_ORDER.reduce((acc, row) => ({ ...acc, [row.key]: 'pending' as StepState }), {}));
    };

    const runResearch = async (q: string, liveOverride: boolean) => {
        const trimmed = q.trim();
        if (!trimmed || searching) return;
        cancelledRef.current = false;
        resetRunState();
        setSearching(true);
        try {
            await agentApi.streamResearch(
                trimmed,
                {
                    onEvent: (event) => {
                        if (cancelledRef.current) return;
                        if (event.type === 'services' && event.services) {
                            setServices(event.services);
                            return;
                        }
                        if (event.type === 'step' && event.step) {
                            const state: StepState =
                                event.status === 'running'
                                    ? 'running'
                                    : event.status === 'done'
                                      ? 'done'
                                      : event.status === 'skipped'
                                        ? 'skipped'
                                        : 'pending';
                            setSteps((prev) => ({ ...prev, [event.step as string]: state }));
                            return;
                        }
                        if (event.type === 'sources' && event.sources) {
                            setSources(event.sources);
                            return;
                        }
                        if (event.type === 'token') {
                            setAnswer((prev) => prev + String(event.text || ''));
                            return;
                        }
                        if (event.type === 'memory_hit') {
                            setMemoryHit({
                                matchPercent: Number(event.match_percent || 0),
                                cachedAt: String(event.cached_at || ''),
                                cachedAgeLabel: String(event.cached_age_label || 'unknown'),
                            });
                            return;
                        }
                        if (event.type === 'error') {
                            setError(String(event.message || 'Research failed.'));
                        }
                    },
                    onDone: (event) => {
                        if (cancelledRef.current) return;
                        setSearching(false);
                        setTimings(event.timings || {});
                        setRawMode(Boolean(event.raw_mode));
                        if (!answer && typeof event.answer === 'string' && event.answer.trim()) {
                            setAnswer(event.answer);
                        }
                    },
                    onError: (message) => {
                        if (cancelledRef.current) return;
                        setError(message);
                    },
                },
                { forceLive: liveOverride, maxResults: 10 },
            );
        } catch (err) {
            if (cancelledRef.current) return;
            setSearching(false);
            setError(err instanceof Error ? err.message : 'Research stream failed.');
        }
    };

    const cancelResearch = () => {
        cancelledRef.current = true;
        setSearching(false);
    };

    const onSubmit = async (event: FormEvent) => {
        event.preventDefault();
        await runResearch(query, forceLive);
    };

    const runSuggested = async (suggested: string) => {
        setQuery(suggested);
        await runResearch(suggested, false);
    };

    const searchLiveInstead = async () => {
        if (!query.trim()) return;
        setForceLive(true);
        await runResearch(query, true);
    };

    return (
        <div className="h-full overflow-auto p-4 md:p-6 space-y-4">
            <section className="rounded-card border border-surface-3 bg-surface-1 p-4">
                <h1 className="text-lg font-semibold text-text-primary">Research</h1>
                <p className="text-xs text-text-secondary mt-1">
                    Claude-style local research: rewrite, search, read, synthesize, cite.
                </p>

                <form onSubmit={onSubmit} className="mt-3 flex flex-col md:flex-row gap-2">
                    <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Ask for current web-backed information..."
                        className="flex-1 bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
                    />
                    <button
                        type="submit"
                        disabled={!query.trim() || searching}
                        className="px-4 py-2 rounded-btn border border-accent-blue/40 text-accent-blue disabled:opacity-40"
                    >
                        {searching ? (
                            <span className="flex items-center gap-1.5">
                                <span className="inline-flex gap-0.5">
                                    <span className="w-1 h-1 rounded-full bg-accent-blue animate-bounce [animation-delay:0ms]" />
                                    <span className="w-1 h-1 rounded-full bg-accent-blue animate-bounce [animation-delay:150ms]" />
                                    <span className="w-1 h-1 rounded-full bg-accent-blue animate-bounce [animation-delay:300ms]" />
                                </span>
                                {activeStepLabel ? activeStepLabel.replace(/\.\.\.$/, '') : 'Researching'}
                            </span>
                        ) : 'Research'}
                    </button>
                    {searching && (
                        <button
                            type="button"
                            onClick={cancelResearch}
                            className="px-4 py-2 rounded-btn border border-surface-4 text-text-secondary hover:border-accent-red/40 hover:text-accent-red"
                        >
                            Cancel
                        </button>
                    )}
                </form>

                <div className="mt-3 flex flex-wrap gap-2">
                    <span className="text-[11px] text-text-secondary">Suggested:</span>
                    {SUGGESTED_QUERIES.map((item) => (
                        <button
                            key={item}
                            onClick={() => runSuggested(item)}
                            className="text-[11px] px-2 py-1 rounded border border-surface-4 bg-surface-0 text-text-secondary hover:text-text-primary hover:border-surface-3"
                        >
                            {item}
                        </button>
                    ))}
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                    {['searxng', 'bing', 'google', 'duckduckgo', 'qdrant', 'ollama'].map((key) => {
                        const svc = services[key];
                        const ok = Boolean(svc?.ok);
                        return (
                            <span
                                key={key}
                                className={`text-[11px] px-2 py-1 rounded border ${serviceBadgeClass(ok)}`}
                                title={svc?.error || svc?.url || key}
                            >
                                {key} {ok ? '●' : '○'}
                            </span>
                        );
                    })}
                </div>

                {memoryHit && (
                    <div className="mt-3 rounded border border-accent-green/40 bg-accent-green/10 p-2 text-xs text-accent-green flex items-center justify-between gap-2">
                        <span>
                            Served from memory · {memoryHit.matchPercent.toFixed(1)}% match · cached {memoryHit.cachedAgeLabel}
                        </span>
                        <button
                            onClick={searchLiveInstead}
                            className="px-2 py-1 rounded border border-accent-green/50 text-accent-green hover:bg-accent-green/10"
                        >
                            Search live instead
                        </button>
                    </div>
                )}

                {error && (
                    <div className="mt-3 rounded border border-accent-red/40 bg-accent-red/10 p-3 text-xs text-accent-red flex items-start justify-between gap-3">
                        <span>{error}</span>
                        {query.trim() && (
                            <button
                                type="button"
                                onClick={() => runResearch(query, forceLive)}
                                className="flex-shrink-0 px-2 py-1 rounded border border-accent-red/50 text-accent-red hover:bg-accent-red/10"
                            >
                                Try Again
                            </button>
                        )}
                    </div>
                )}
                {!error && offlineServices.length > 0 && (
                    <div className="mt-3 rounded border border-accent-amber/30 bg-accent-amber/10 p-2 text-xs text-accent-amber">
                        Some services are offline: {offlineServices.join(', ')}. The pipeline still attempts available sources.
                    </div>
                )}
                <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                        <p className="text-[11px] text-text-muted">Trust</p>
                        <p className="mt-1 text-xs text-text-primary">{trustLabel}</p>
                    </div>
                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                        <p className="text-[11px] text-text-muted">Sources</p>
                        <p className="mt-1 text-xs text-text-primary">{sourceCount}</p>
                    </div>
                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                        <p className="text-[11px] text-text-muted">Status</p>
                        <p className="mt-1 text-xs text-text-primary">{searching ? (activeStepLabel || 'Working') : 'Ready'}</p>
                    </div>
                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                        <p className="text-[11px] text-text-muted">Mode</p>
                        <p className="mt-1 text-xs text-text-primary">{forceLive ? 'Forced live' : 'Auto'}</p>
                    </div>
                </div>
                {freshnessNeeded && !forceLive && (
                    <div className="mt-3 rounded border border-accent-blue/30 bg-accent-blue/10 p-2 text-xs text-accent-blue">
                        This query looks freshness-sensitive. Auto mode is active; switch to live mode if you want to bypass memory for this run.
                    </div>
                )}
            </section>

            <section className="rounded-card border border-surface-3 bg-surface-1 p-4 space-y-3">
                <h2 className="text-sm font-semibold text-text-primary">Pipeline</h2>
                <div className="space-y-1">
                    {STEP_ORDER.map((step) => (
                        <div key={step.key} className="text-xs text-text-secondary flex items-center gap-2">
                            <span className="w-4 text-center">{statusGlyph(steps[step.key] || 'pending')}</span>
                            <span>{step.label}</span>
                        </div>
                    ))}
                </div>

                <div>
                    <div className="flex items-center justify-between gap-2 mb-1">
                        <h3 className="text-xs font-semibold text-text-primary">Sources</h3>
                        {sourceCount > 0 && (
                            <span className="text-[11px] text-text-muted">
                                using {Math.min(sourceCount, 3)} primary source{sourceCount === 1 ? '' : 's'}
                            </span>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {rankedSources.length === 0 && <span className="text-xs text-text-muted">No sources yet.</span>}
                        {rankedSources.map((row, idx) => (
                            <a
                                key={`${row.url}-${idx}`}
                                href={row.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-[11px] px-2 py-1 rounded border border-accent-blue/30 text-accent-blue hover:bg-accent-blue/10"
                                title={row.url}
                            >
                                [{idx + 1}] {row.title} {sourceDomain(row.url) ? `· ${sourceDomain(row.url)}` : ''}
                            </a>
                        ))}
                    </div>
                </div>
                {rankedSources.length > 0 && (
                    <div className="space-y-2">
                        <h3 className="text-xs font-semibold text-text-primary">Top evidence</h3>
                        {rankedSources.slice(0, 3).map((row, idx) => (
                            <div key={`${row.url}-evidence-${idx}`} className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                    <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">#{idx + 1}</span>
                                    {row.provider && (
                                        <span className="rounded-full border border-surface-4 px-2 py-1 text-text-secondary">{row.provider}</span>
                                    )}
                                    {row.engine && (
                                        <span className="rounded-full border border-surface-4 px-2 py-1 text-text-secondary">{row.engine}</span>
                                    )}
                                    <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-accent">
                                        {confidenceLabel((row as { score?: number }).score)}
                                    </span>
                                    {sourceDomain(row.url) && (
                                        <span className="text-text-muted">{sourceDomain(row.url)}</span>
                                    )}
                                </div>
                                <a
                                    href={row.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="mt-2 block text-sm text-text-primary hover:text-accent"
                                >
                                    {row.title}
                                </a>
                                <p className="mt-1 text-xs text-text-secondary">{row.snippet}</p>
                            </div>
                        ))}
                    </div>
                )}
            </section>

            <section className="rounded-card border border-surface-3 bg-surface-1 p-4 space-y-3">
                <h2 className="text-sm font-semibold text-text-primary">Answer</h2>
                {compactSummary && (
                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                        <p className="text-[11px] uppercase tracking-wide text-text-secondary">Compact Summary</p>
                        <p className="mt-2 text-sm text-text-primary">{compactSummaryLine}</p>
                    </div>
                )}
                {!answer && (
                    <p className="text-xs text-text-secondary flex items-center gap-1.5">
                        {searching ? (
                            <>
                                <span className="inline-flex gap-0.5">
                                    <span className="w-1 h-1 rounded-full bg-text-secondary animate-bounce [animation-delay:0ms]" />
                                    <span className="w-1 h-1 rounded-full bg-text-secondary animate-bounce [animation-delay:150ms]" />
                                    <span className="w-1 h-1 rounded-full bg-text-secondary animate-bounce [animation-delay:300ms]" />
                                </span>
                                {activeStepLabel || 'Streaming answer...'}
                            </>
                        ) : 'Run a research query to stream grounded results.'}
                    </p>
                )}
                {answer && (
                    <div className="prose prose-invert prose-sm max-w-none">
                        <ReactMarkdown>{answer}</ReactMarkdown>
                    </div>
                )}
                {sourceCount > 0 && (
                    <p className="text-[11px] text-text-muted">
                        Trust note: citations are only as reliable as the fetched pages. Open the source chips above when you need to verify a claim directly.
                    </p>
                )}
                {rawMode && (
                    <p className="text-xs text-accent-amber">
                        Returned raw source summary because Ollama synthesis was unavailable.
                    </p>
                )}
                {Object.keys(timings).length > 0 && (
                    <div className="text-[11px] text-text-muted border-t border-surface-3 pt-2">
                        {Object.entries(timings).map(([key, value]) => (
                            <span key={key} className="mr-3">
                                {key}: {Number(value).toFixed(3)}s
                            </span>
                        ))}
                    </div>
                )}
            </section>
        </div>
    );
}
