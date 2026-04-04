import { useCallback, useEffect, useMemo, useState } from 'react';
import * as agentApi from '../lib/agentSpaceApi';
import { PageHeader } from '../components/PageHeader';

type AuditMode = 'quick' | 'deep';

function formatTime(epochSeconds: number): string {
    if (!Number.isFinite(epochSeconds) || epochSeconds <= 0) return 'n/a';
    return new Date(epochSeconds * 1000).toLocaleString();
}

function statusTone(status: 'pass' | 'warn' | 'fail' | 'info'): string {
    if (status === 'pass') return 'border-accent-green/40 bg-accent-green/10 text-accent-green';
    if (status === 'warn') return 'border-accent-amber/40 bg-accent-amber/10 text-accent-amber';
    if (status === 'fail') return 'border-accent-red/40 bg-accent-red/10 text-accent-red';
    return 'border-surface-4 bg-surface-0 text-text-secondary';
}

function statusDotClass(status: 'pass' | 'warn' | 'fail' | 'info'): string {
    if (status === 'pass') return 'bg-accent-green';
    if (status === 'warn') return 'bg-accent-amber';
    if (status === 'fail') return 'bg-accent-red';
    return 'bg-surface-4';
}

export default function SystemAudit() {
    const [audit, setAudit] = useState<agentApi.SystemAuditResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [includeResearchProbe, setIncludeResearchProbe] = useState(false);
    const [includeBrowserProbe, setIncludeBrowserProbe] = useState(false);

    const runAudit = useCallback(async (mode: AuditMode) => {
        setLoading(true);
        setError('');
        setMessage('');
        try {
            const deep = mode === 'deep';
            const data = await agentApi.getSystemAudit({
                include_research_probe: deep || includeResearchProbe,
                include_browser_probe: deep || includeBrowserProbe,
            });
            setAudit(data);
            setMessage(
                deep
                    ? 'Deep audit completed (includes research/browser probes).'
                    : 'Quick audit completed.',
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : 'System audit failed.');
        } finally {
            setLoading(false);
        }
    }, [includeBrowserProbe, includeResearchProbe]);

    useEffect(() => {
        runAudit('quick').catch(() => {});
    }, [runAudit]);

    const sortedChecks = useMemo(
        () => (audit?.checks || []).slice().sort((a, b) => {
            const rank = { fail: 0, warn: 1, pass: 2, info: 3 } as const;
            return rank[a.status] - rank[b.status];
        }),
        [audit?.checks],
    );

    return (
        <div className="h-full overflow-auto space-y-4 p-5 md:p-8">
            <PageHeader
                title="System Audit"
                description="Run a full readiness audit across power, policy, model runtime, state stores, and run health."
                actions={
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            disabled={loading}
                            onClick={() => runAudit('quick')}
                            className="px-3 py-2 rounded-btn border border-accent-blue/40 text-accent-blue text-xs disabled:opacity-60"
                        >
                            {loading ? 'Running...' : 'Run Quick Audit'}
                        </button>
                        <button
                            type="button"
                            disabled={loading}
                            onClick={() => runAudit('deep')}
                            className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green text-xs disabled:opacity-60"
                        >
                            {loading ? 'Running...' : 'Run Deep Audit'}
                        </button>
                    </div>
                }
            />
            <section className="rounded-card border border-surface-4 bg-surface-1 p-4 space-y-3">
                <div className="grid md:grid-cols-2 gap-2">
                    <Toggle
                        label="Include Web Research Probe"
                        enabled={includeResearchProbe}
                        onToggle={() => setIncludeResearchProbe((v) => !v)}
                    />
                    <Toggle
                        label="Include Browser Probe"
                        enabled={includeBrowserProbe}
                        onToggle={() => setIncludeBrowserProbe((v) => !v)}
                    />
                </div>
                {audit && (
                    <p className="text-xs text-text-secondary">
                        overall: <span className="text-text-primary">{audit.overall_status}</span> • generated: {formatTime(audit.generated_at)}
                    </p>
                )}
            </section>

            {audit && (
                <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                    <div className="grid md:grid-cols-4 gap-2">
                        <Stat label="Total" value={audit.summary.total} />
                        <Stat label="Pass" value={audit.summary.pass} tone="pass" />
                        <Stat label="Warn" value={audit.summary.warn} tone="warn" />
                        <Stat label="Fail" value={audit.summary.fail} tone="fail" />
                    </div>
                </section>
            )}

            <section className="rounded-card border border-surface-4 bg-surface-1 p-4 space-y-2">
                <h2 className="text-base font-semibold text-text-primary">Checks</h2>
                {sortedChecks.length === 0 && (
                    <p className="text-xs text-text-secondary">No audit results yet.</p>
                )}
                {sortedChecks.map((check) => (
                    <div key={check.id} className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                        <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                                <span className={`w-2 h-2 rounded-none flex-shrink-0 ${statusDotClass(check.status)}`} />
                                <p className="text-sm text-text-primary truncate">{check.title}</p>
                            </div>
                            <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-btn border flex-shrink-0 ${statusTone(check.status)}`}>
                                {check.status}
                            </span>
                        </div>
                        <p className="text-xs text-text-secondary mt-1">{check.summary}</p>
                        {audit && (
                            <p className="text-[10px] text-text-muted mt-1">
                                Last checked: {formatTime(audit.generated_at)}
                            </p>
                        )}
                        {check.details && Object.keys(check.details).length > 0 && (
                            <pre className="mt-2 text-[11px] text-text-muted whitespace-pre-wrap rounded-btn border border-surface-4 bg-surface-1 p-2">
                                {JSON.stringify(check.details, null, 2)}
                            </pre>
                        )}
                    </div>
                ))}
            </section>

            {message && <p className="text-sm text-accent-green">{message}</p>}
            {error && <p className="text-sm text-accent-red">{error}</p>}
        </div>
    );
}

function Toggle({
    label,
    enabled,
    onToggle,
}: {
    label: string;
    enabled: boolean;
    onToggle: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onToggle}
            className={`rounded-btn border px-3 py-2 text-left ${enabled ? 'border-accent-green/50 bg-accent-green/10' : 'border-surface-4 bg-surface-0'}`}
        >
            <p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p>
            <p className="text-sm text-text-primary mt-1">{enabled ? 'ON' : 'OFF'}</p>
        </button>
    );
}

function Stat({
    label,
    value,
    tone = 'default',
}: {
    label: string;
    value: number;
    tone?: 'default' | 'pass' | 'warn' | 'fail';
}) {
    const color = tone === 'pass'
        ? 'text-accent-green'
        : tone === 'warn'
            ? 'text-accent-amber'
            : tone === 'fail'
                ? 'text-accent-red'
                : 'text-text-primary';
    return (
        <div className="rounded-btn border border-surface-4 bg-surface-0 p-3">
            <p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p>
            <p className={`text-lg font-semibold mt-1 ${color}`}>{value}</p>
        </div>
    );
}
