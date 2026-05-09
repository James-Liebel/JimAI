import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Brain, Lightbulb, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { PageHeader, PageSection } from '../components/PageHeader';
import * as api from '../lib/autonomyApi';

type TabKey = 'memory' | 'skills' | 'reflections' | 'heartbeat';

const TABS: { key: TabKey; label: string; icon: typeof Brain }[] = [
    { key: 'memory', label: 'Episodic memory', icon: Brain },
    { key: 'skills', label: 'Skill library', icon: Sparkles },
    { key: 'reflections', label: 'Reflections', icon: Lightbulb },
    { key: 'heartbeat', label: 'Heartbeat', icon: Activity },
];

function formatRelative(ts: number): string {
    if (!ts) return '—';
    const ms = ts > 1e12 ? ts : ts * 1000;
    const delta = Date.now() - ms;
    if (delta < 0) return `in ${Math.abs(Math.round(delta / 1000))}s`;
    if (delta < 60_000) return `${Math.round(delta / 1000)}s ago`;
    if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
    if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h ago`;
    return `${Math.round(delta / 86_400_000)}d ago`;
}

function StatGrid({ rows }: { rows: { label: string; value: string | number }[] }) {
    return (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {rows.map((row) => (
                <div key={row.label} className="rounded-md border border-surface-4 bg-surface-2 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-text-muted">{row.label}</div>
                    <div className="mt-1 font-mono text-lg text-text-primary">{row.value ?? '—'}</div>
                </div>
            ))}
        </div>
    );
}

export default function Autonomy() {
    const [tab, setTab] = useState<TabKey>('memory');
    const [memStats, setMemStats] = useState<Record<string, number>>({});
    const [memRecent, setMemRecent] = useState<api.EpisodeRecord[]>([]);
    const [memQuery, setMemQuery] = useState('');
    const [memHits, setMemHits] = useState<(api.EpisodeRecord & { score: number })[]>([]);
    const [skillStats, setSkillStats] = useState<Record<string, unknown>>({});
    const [skills, setSkills] = useState<api.SkillEntry[]>([]);
    const [refStats, setRefStats] = useState<Record<string, unknown>>({});
    const [refQuery, setRefQuery] = useState('');
    const [refResults, setRefResults] = useState<api.ReflectionTrace[]>([]);
    const [hbStatus, setHbStatus] = useState<api.HeartbeatStatus | null>(null);
    const [hbJobs, setHbJobs] = useState<api.HeartbeatJob[]>([]);
    const [newJobName, setNewJobName] = useState('');
    const [newJobObjective, setNewJobObjective] = useState('');
    const [newJobInterval, setNewJobInterval] = useState(900);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const refresh = useCallback(async () => {
        setError('');
        try {
            const [m, mr, ss, sl, rs, hs, hj] = await Promise.all([
                api.memoryStats(),
                api.memoryRecent(40),
                api.skillStats(),
                api.skillList(100),
                api.reflectionStats(),
                api.heartbeatStatus(),
                api.heartbeatJobs(),
            ]);
            setMemStats(m);
            setMemRecent(mr.items);
            setSkillStats(ss);
            setSkills(sl.items);
            setRefStats(rs);
            setHbStatus(hs);
            setHbJobs(hj.items);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'Failed to load autonomy data.');
        }
    }, []);

    useEffect(() => {
        refresh().catch(() => undefined);
        const id = window.setInterval(() => {
            refresh().catch(() => undefined);
        }, 15_000);
        return () => window.clearInterval(id);
    }, [refresh]);

    const memorySearchSubmit = async () => {
        if (!memQuery.trim()) return;
        setBusy(true);
        try {
            const res = await api.memorySearch(memQuery, 6);
            setMemHits(res.results);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'search failed');
        } finally {
            setBusy(false);
        }
    };

    const reflectionLookupSubmit = async () => {
        if (!refQuery.trim()) return;
        setBusy(true);
        try {
            const res = await api.reflectionLookup(refQuery, 6);
            setRefResults(res.lessons);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'lookup failed');
        } finally {
            setBusy(false);
        }
    };

    const consolidateMemory = async () => {
        setBusy(true);
        try {
            await api.memoryConsolidate(3);
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'consolidate failed');
        } finally {
            setBusy(false);
        }
    };

    const heartbeatToggle = async () => {
        setBusy(true);
        try {
            if (hbStatus?.running) await api.heartbeatStop();
            else await api.heartbeatStart();
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'heartbeat toggle failed');
        } finally {
            setBusy(false);
        }
    };

    const heartbeatTickNow = async () => {
        setBusy(true);
        try {
            await api.heartbeatTick();
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'tick failed');
        } finally {
            setBusy(false);
        }
    };

    const heartbeatAdd = async () => {
        if (!newJobName.trim() || !newJobObjective.trim()) return;
        setBusy(true);
        try {
            await api.heartbeatAddJob({
                name: newJobName.trim(),
                objective: newJobObjective.trim(),
                interval_seconds: Math.max(30, Number(newJobInterval) || 900),
            });
            setNewJobName('');
            setNewJobObjective('');
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'add job failed');
        } finally {
            setBusy(false);
        }
    };

    const heartbeatDelete = async (id: string) => {
        setBusy(true);
        try {
            await api.heartbeatDeleteJob(id);
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'delete job failed');
        } finally {
            setBusy(false);
        }
    };

    const memoryStatsRows = useMemo(
        () => [
            { label: 'episodes', value: memStats.count ?? 0 },
            { label: 'embedded', value: memStats.embedded ?? 0 },
            { label: 'runs covered', value: memStats.runs ?? 0 },
            { label: 'first seen', value: formatRelative(memStats.first_at ?? 0) },
        ],
        [memStats],
    );

    return (
        <div className="space-y-6 p-6">
            <PageHeader
                title="Autonomy"
                description="Live view of the agent platform's self-direction primitives — memory, skill library, reflections, and the heartbeat scheduler."
                meta={
                    error ? (
                        <span className="text-status-error">{error}</span>
                    ) : (
                        <span>auto-refreshes every 15s</span>
                    )
                }
                actions={
                    <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm hover:bg-surface-3"
                        onClick={() => refresh().catch(() => undefined)}
                    >
                        <RefreshCw className="h-4 w-4" /> Refresh
                    </button>
                }
            />

            <div className="flex flex-wrap gap-2">
                {TABS.map((t) => {
                    const Icon = t.icon;
                    const active = tab === t.key;
                    return (
                        <button
                            type="button"
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition ${
                                active
                                    ? 'border border-accent-1 bg-accent-1/10 text-accent-1'
                                    : 'border border-surface-4 bg-surface-2 text-text-secondary hover:bg-surface-3'
                            }`}
                        >
                            <Icon className="h-4 w-4" /> {t.label}
                        </button>
                    );
                })}
            </div>

            {tab === 'memory' && (
                <PageSection title="Episodic memory">
                    <StatGrid rows={memoryStatsRows} />
                    <div className="mt-4 flex gap-2">
                        <input
                            value={memQuery}
                            onChange={(e) => setMemQuery(e.target.value)}
                            placeholder="search past runs..."
                            className="flex-1 rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                        />
                        <button
                            type="button"
                            disabled={busy}
                            onClick={memorySearchSubmit}
                            className="rounded-md border border-accent-1 bg-accent-1/10 px-3 py-1.5 text-sm text-accent-1 hover:bg-accent-1/20"
                        >
                            Search
                        </button>
                        <button
                            type="button"
                            disabled={busy}
                            onClick={consolidateMemory}
                            className="rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm hover:bg-surface-3"
                            title="Squash older episodes into compact summaries"
                        >
                            Consolidate
                        </button>
                    </div>
                    {memHits.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                            <div className="text-[11px] uppercase tracking-wide text-text-muted">Search results</div>
                            {memHits.map((h) => (
                                <div key={h.id} className="rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                                    <div className="mb-1 flex items-center justify-between font-mono text-[11px] text-text-muted">
                                        <span>{h.event}</span>
                                        <span>score {h.score.toFixed(2)} · {formatRelative(h.timestamp)}</span>
                                    </div>
                                    <div className="text-text-primary">{h.summary}</div>
                                </div>
                            ))}
                        </div>
                    )}
                    <div className="mt-4">
                        <div className="text-[11px] uppercase tracking-wide text-text-muted">Recent</div>
                        <div className="mt-2 space-y-1.5">
                            {memRecent.map((row) => (
                                <div key={row.id} className="rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                                    <div className="mb-1 flex items-center justify-between font-mono text-[11px] text-text-muted">
                                        <span>{row.event} ({row.outcome})</span>
                                        <span>{formatRelative(row.timestamp)}</span>
                                    </div>
                                    <div className="text-text-primary">{row.summary}</div>
                                </div>
                            ))}
                            {memRecent.length === 0 && <div className="text-sm text-text-muted">No episodes yet.</div>}
                        </div>
                    </div>
                </PageSection>
            )}

            {tab === 'skills' && (
                <PageSection title="Skill library">
                    <StatGrid
                        rows={[
                            { label: 'skills', value: String(skillStats.count ?? 0) },
                            { label: 'embedded', value: String(skillStats.embedded ?? 0) },
                            { label: 'total uses', value: String(skillStats.total_uses ?? 0) },
                            { label: 'avg success', value: String(skillStats.avg_success ?? 0) },
                        ]}
                    />
                    <div className="mt-4 space-y-1.5">
                        {skills.map((s) => (
                            <div key={s.id} className="rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                                <div className="flex items-center justify-between">
                                    <div className="font-medium text-text-primary">{s.name}</div>
                                    <div className="font-mono text-[11px] text-text-muted">
                                        {s.artifact_type} · success {s.success_count} · uses {s.use_count}
                                    </div>
                                </div>
                                <div className="mt-1 text-text-secondary">{s.description || s.objective.slice(0, 200)}</div>
                                {s.tags.length > 0 && (
                                    <div className="mt-1 flex flex-wrap gap-1 text-[11px] text-text-muted">
                                        {s.tags.map((t) => (
                                            <span key={t} className="rounded bg-surface-3 px-1.5">
                                                {t}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                        {skills.length === 0 && (
                            <div className="text-sm text-text-muted">
                                No skills captured yet — successful runs will appear here automatically.
                            </div>
                        )}
                    </div>
                </PageSection>
            )}

            {tab === 'reflections' && (
                <PageSection title="Reflections">
                    <StatGrid
                        rows={[
                            { label: 'lessons', value: String(refStats.count ?? 0) },
                            { label: 'runs covered', value: String(refStats.runs ?? 0) },
                            { label: 'max attempts', value: String(refStats.max_attempts_seen ?? 0) },
                            { label: 'last lesson', value: formatRelative((refStats.last_at as number) ?? 0) },
                        ]}
                    />
                    <div className="mt-4 flex gap-2">
                        <input
                            value={refQuery}
                            onChange={(e) => setRefQuery(e.target.value)}
                            placeholder="objective to look up lessons for..."
                            className="flex-1 rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                        />
                        <button
                            type="button"
                            disabled={busy}
                            onClick={reflectionLookupSubmit}
                            className="rounded-md border border-accent-1 bg-accent-1/10 px-3 py-1.5 text-sm text-accent-1 hover:bg-accent-1/20"
                        >
                            Lookup
                        </button>
                    </div>
                    {refResults.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                            {refResults.map((r) => (
                                <div key={r.id} className="rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                                    <div className="mb-1 font-mono text-[11px] text-text-muted">
                                        attempt {r.attempt} · {formatRelative(r.created_at)} · {r.objective.slice(0, 80)}
                                    </div>
                                    <div className="text-text-primary">{r.lesson}</div>
                                </div>
                            ))}
                        </div>
                    )}
                </PageSection>
            )}

            {tab === 'heartbeat' && (
                <PageSection title="Heartbeat scheduler">
                    <div className="flex flex-wrap items-center gap-3">
                        <span
                            className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${
                                hbStatus?.running ? 'bg-status-success/10 text-status-success' : 'bg-status-warning/10 text-status-warning'
                            }`}
                        >
                            <span className="h-2 w-2 rounded-full bg-current" /> {hbStatus?.running ? 'running' : 'stopped'}
                        </span>
                        <span className="font-mono text-[11px] text-text-muted">
                            tick every {hbStatus?.tick_interval_seconds ?? 60}s · {hbStatus?.job_count ?? 0} jobs ·
                            last fired {hbStatus?.last_tick_fired ?? 0} · {formatRelative(hbStatus?.last_tick_at ?? 0)}
                        </span>
                        <button
                            type="button"
                            disabled={busy}
                            onClick={heartbeatToggle}
                            className="rounded-md border border-accent-1 bg-accent-1/10 px-3 py-1.5 text-sm text-accent-1 hover:bg-accent-1/20"
                        >
                            {hbStatus?.running ? 'Stop' : 'Start'}
                        </button>
                        <button
                            type="button"
                            disabled={busy}
                            onClick={heartbeatTickNow}
                            className="rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm hover:bg-surface-3"
                        >
                            Tick now
                        </button>
                    </div>

                    <div className="mt-4 grid gap-2 md:grid-cols-3">
                        <input
                            value={newJobName}
                            onChange={(e) => setNewJobName(e.target.value)}
                            placeholder="Job name (e.g. nightly-self-improve)"
                            className="rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                        />
                        <input
                            value={newJobObjective}
                            onChange={(e) => setNewJobObjective(e.target.value)}
                            placeholder="Objective the agent should pursue"
                            className="rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm md:col-span-2"
                        />
                        <input
                            type="number"
                            min={30}
                            value={newJobInterval}
                            onChange={(e) => setNewJobInterval(Number(e.target.value))}
                            className="rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                            placeholder="Interval (seconds)"
                        />
                        <button
                            type="button"
                            disabled={busy || !newJobName || !newJobObjective}
                            onClick={heartbeatAdd}
                            className="rounded-md border border-accent-1 bg-accent-1/10 px-3 py-1.5 text-sm text-accent-1 hover:bg-accent-1/20 md:col-span-2"
                        >
                            Add job
                        </button>
                    </div>

                    <div className="mt-4 space-y-1.5">
                        {hbJobs.map((j) => (
                            <div key={j.id} className="flex items-center justify-between rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                                <div>
                                    <div className="font-medium text-text-primary">{j.name}</div>
                                    <div className="font-mono text-[11px] text-text-muted">
                                        every {j.interval_seconds}s · fired {j.fire_count} · last {formatRelative(j.last_fired_at)} ·
                                        {j.enabled ? ' enabled' : ' disabled'} {j.one_shot ? '· one-shot' : ''}
                                    </div>
                                    <div className="text-text-secondary">{j.objective}</div>
                                    {j.last_error && <div className="text-status-error text-[11px]">{j.last_error}</div>}
                                </div>
                                <button
                                    type="button"
                                    onClick={() => heartbeatDelete(j.id)}
                                    className="rounded-md border border-surface-4 bg-surface-2 p-1.5 text-text-secondary hover:bg-surface-3"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </button>
                            </div>
                        ))}
                        {hbJobs.length === 0 && <div className="text-sm text-text-muted">No heartbeat jobs configured.</div>}
                    </div>
                </PageSection>
            )}
        </div>
    );
}
