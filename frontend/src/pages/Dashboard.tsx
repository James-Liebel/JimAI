import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import * as agentApi from '../lib/agentSpaceApi';

type StatusPayload = {
    power: { enabled: boolean; release_gpu_on_off?: boolean };
    settings: Record<string, unknown>;
    metrics: Record<string, number>;
    active_runs: agentApi.AgentSpaceRunSummary[];
};

export default function Dashboard() {
    const [status, setStatus] = useState<StatusPayload | null>(null);
    const [runs, setRuns] = useState<agentApi.AgentSpaceRunSummary[]>([]);
    const [memory, setMemory] = useState<Array<Record<string, unknown>>>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [lastUpdatedLabel, setLastUpdatedLabel] = useState('');
    const [consecutiveFailures, setConsecutiveFailures] = useState(0);
    const consecutiveFailuresRef = useRef(0);

    const load = useCallback(async () => {
        try {
            const [statusData, runData, memoryData] = await Promise.all([
                agentApi.getAgentSpaceStatus(),
                agentApi.listRuns(20),
                agentApi.recentMemory(8),
            ]);
            setStatus(statusData);
            setRuns(runData);
            setMemory(memoryData);
            setError('');
            consecutiveFailuresRef.current = 0;
            setConsecutiveFailures(0);
            const now = new Date();
            setLastUpdated(now);
        } catch (err) {
            consecutiveFailuresRef.current += 1;
            setConsecutiveFailures(consecutiveFailuresRef.current);
            setError(err instanceof Error ? err.message : 'Failed to load dashboard.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
        const id = window.setInterval(load, 5000);
        return () => window.clearInterval(id);
    }, [load]);

    useEffect(() => {
        const tick = () => {
            if (!lastUpdated) { setLastUpdatedLabel(''); return; }
            const secs = Math.round((Date.now() - lastUpdated.getTime()) / 1000);
            if (secs < 5) setLastUpdatedLabel('just now');
            else if (secs < 60) setLastUpdatedLabel(`${secs}s ago`);
            else setLastUpdatedLabel(`${Math.round(secs / 60)}m ago`);
        };
        tick();
        const id = window.setInterval(tick, 5000);
        return () => window.clearInterval(id);
    }, [lastUpdated]);

    const metrics = status?.metrics ?? {};
    const runState = useMemo(() => {
        const power = status?.power?.enabled ? 'ON' : 'OFF';
        return `${power} • ${status?.active_runs?.length ?? 0} active run(s)`;
    }, [status]);

    const togglePower = useCallback(async () => {
        if (!status) return;
        await agentApi.setPowerState(!status.power.enabled, status.power.release_gpu_on_off);
        await load();
    }, [load, status]);

    if (loading && !status) return <div className="p-6 text-text-secondary">Loading dashboard...</div>;

    return (
        <div className="h-full overflow-auto p-5 md:p-8">
            <div className="mx-auto w-full max-w-6xl space-y-6">
            {consecutiveFailures >= 2 && (
                <div className="rounded-card border border-accent-amber/40 bg-accent-amber/10 px-4 py-3 flex items-center gap-3">
                    <span className="w-2 h-2 rounded-full bg-accent-amber animate-pulse flex-shrink-0" />
                    <p className="text-xs text-accent-amber flex-1">
                        Backend connection lost. Attempting to reconnect...
                    </p>
                </div>
            )}

            <section className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <h1 className="text-lg md:text-xl font-semibold text-text-primary">jimAI Dashboard</h1>
                        <p className="text-xs md:text-sm text-text-secondary">{runState}</p>
                        {lastUpdatedLabel && (
                            <p className="text-[11px] text-text-muted mt-0.5">Last updated: {lastUpdatedLabel}</p>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={togglePower}
                            className={`px-4 py-2 rounded-btn text-sm font-semibold border ${
                                status?.power?.enabled
                                    ? 'bg-accent-red/15 border-accent-red/50 text-accent-red'
                                    : 'bg-accent-green/15 border-accent-green/50 text-accent-green'
                            }`}
                        >
                            {status?.power?.enabled ? 'Turn OFF' : 'Turn ON'}
                        </button>
                        <Link to="/audit" className="px-4 py-2 rounded-btn border border-accent/40 text-sm text-accent hover:bg-accent/10">
                            Run Audit
                        </Link>
                        <Link to="/self-code" className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary hover:bg-surface-2">
                            Start Run
                        </Link>
                    </div>
                </div>
                {error && (
                    <div className="mt-3 flex items-center gap-3">
                        <p className="text-xs text-accent-red flex-1">{error}</p>
                        <button
                            onClick={load}
                            className="flex-shrink-0 px-3 py-1.5 rounded-btn border border-accent-red/40 text-accent-red text-xs hover:bg-accent-red/10"
                        >
                            Retry
                        </button>
                    </div>
                )}
            </section>

            <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricCard label="Runs Started" value={metrics.runs_started ?? 0} />
                <MetricCard label="Runs Completed" value={metrics.runs_completed ?? 0} />
                <MetricCard label="Actions" value={metrics.actions_total ?? 0} />
                <MetricCard label="Reviews Applied" value={metrics.reviews_applied ?? 0} />
            </section>

            <section className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                <div className="flex items-center justify-between">
                    <h2 className="text-sm md:text-base font-semibold text-text-primary">Recent Runs</h2>
                    <Link to="/workflow" className="text-xs text-accent hover:underline">Open Workflow Review</Link>
                </div>
                <div className="mt-4 space-y-3">
                    {runs.length === 0 && <p className="text-xs text-text-secondary">No runs yet.</p>}
                    {runs.map((run) => (
                        <div key={run.id} className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                            <div className="flex items-center justify-between gap-2">
                                <p className="text-sm font-medium text-text-primary truncate">{run.objective}</p>
                                <span className={`text-xs px-2 py-1 rounded ${
                                    run.status === 'completed' ? 'bg-accent-green/15 text-accent-green'
                                        : run.status === 'failed' ? 'bg-accent-red/15 text-accent-red'
                                            : run.status === 'running' ? 'bg-accent/15 text-accent'
                                                : 'bg-surface-2 text-text-secondary'
                                }`}>
                                    {run.status}
                                </span>
                            </div>
                            <p className="text-[11px] text-text-muted mt-1">
                                actions: {run.action_count} • reviews: {run.review_ids.length} • snapshots: {run.snapshot_ids.length}
                            </p>
                        </div>
                    ))}
                </div>
            </section>

            <section className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                <h2 className="text-sm md:text-base font-semibold text-text-primary">Recent Memory Summaries</h2>
                <div className="mt-4 space-y-3">
                    {memory.length === 0 && <p className="text-xs text-text-secondary">No memory entries yet.</p>}
                    {memory.map((entry, index) => (
                        <div key={index} className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                            <p className="text-sm text-text-primary">{String(entry.objective || 'Untitled run')}</p>
                            <p className="text-[11px] text-text-muted mt-1">
                                status: {String(entry.status || 'unknown')} • run: {String(entry.run_id || '')}
                            </p>
                        </div>
                    ))}
                </div>
            </section>
            </div>
        </div>
    );
}

function MetricCard({ label, value }: { label: string; value: number }) {
    return (
        <div className="rounded-card border border-surface-3 bg-surface-1 p-4">
            <p className="text-xs uppercase tracking-wide text-text-secondary">{label}</p>
            <p className="mt-2 text-2xl font-semibold text-text-primary">{value}</p>
        </div>
    );
}
