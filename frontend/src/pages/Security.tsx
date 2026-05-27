import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { PageHeader, PageSection } from '../components/PageHeader';
import { Button } from '../components/ui/Button';
import * as api from '../lib/securityApi';

function formatRelative(ts: number): string {
    if (!ts) return '—';
    const ms = ts > 1e12 ? ts : ts * 1000;
    const delta = Date.now() - ms;
    if (delta < 60_000) return `${Math.round(delta / 1000)}s ago`;
    if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
    if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h ago`;
    return `${Math.round(delta / 86_400_000)}d ago`;
}

function StatTile({ label, value, accent }: { label: string; value: string | number; accent?: 'good' | 'warn' | 'bad' }) {
    const color =
        accent === 'good'
            ? 'text-status-success'
            : accent === 'warn'
                ? 'text-status-warning'
                : accent === 'bad'
                    ? 'text-status-error'
                    : 'text-text-primary';
    return (
        <div className="rounded-md border border-surface-4 bg-surface-2 p-3">
            <div className="text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
            <div className={`mt-1 font-mono text-lg ${color}`}>{value}</div>
        </div>
    );
}

export default function Security() {
    const [overview, setOverview] = useState<api.SecurityOverview | null>(null);
    const [shieldText, setShieldText] = useState('');
    const [shieldVerdict, setShieldVerdict] = useState<api.ShieldVerdict | null>(null);
    const [shieldUseGuardrail, setShieldUseGuardrail] = useState(false);
    const [shieldGuardrailModel, setShieldGuardrailModel] = useState('');
    const [secretText, setSecretText] = useState('');
    const [secretFindings, setSecretFindings] = useState<api.SecretFinding[]>([]);
    const [policies, setPolicies] = useState<api.ToolPolicy[]>([]);
    const [audit, setAudit] = useState<{ id: string; timestamp: number; agent_id: string; tool: string; decision: string; reasons: string[] }[]>([]);
    const [egressUrl, setEgressUrl] = useState('');
    const [egressVerdict, setEgressVerdict] = useState<api.EgressVerdict | null>(null);
    const [egressNewDomain, setEgressNewDomain] = useState('');
    const [supplyLatest, setSupplyLatest] = useState<api.SupplyChainReport | null>(null);
    const [supplyDiff, setSupplyDiff] = useState<{ new_count: number; resolved_count: number; new_findings: api.SupplyChainReport['findings'] } | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    const refresh = useCallback(async () => {
        setError('');
        try {
            const [ov, p, a, sl, sd] = await Promise.all([
                api.securityOverview(),
                api.toolGatePolicies(),
                api.toolGateAudit(50),
                api.supplyChainLatest(),
                api.supplyChainDiff(),
            ]);
            setOverview(ov);
            setPolicies(p.policies);
            setAudit(a.items);
            setSupplyLatest(sl);
            setSupplyDiff(sd);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'Failed to load security data.');
        }
    }, []);

    useEffect(() => {
        refresh().catch(() => undefined);
        const id = window.setInterval(() => {
            refresh().catch(() => undefined);
        }, 20_000);
        return () => window.clearInterval(id);
    }, [refresh]);

    const runShield = async () => {
        if (!shieldText.trim()) return;
        setBusy(true);
        try {
            const v = await api.shieldCheck(shieldText, { useGuardrail: shieldUseGuardrail });
            setShieldVerdict(v);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'shield check failed');
        } finally {
            setBusy(false);
        }
    };

    const setGuardrail = async () => {
        setBusy(true);
        try {
            await api.shieldSetGuardrailModel(shieldGuardrailModel.trim() || null);
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'set guardrail failed');
        } finally {
            setBusy(false);
        }
    };

    const runSecretScan = async () => {
        if (!secretText.trim()) return;
        setBusy(true);
        try {
            const r = await api.secretsScan(secretText);
            setSecretFindings(r.findings);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'scan failed');
        } finally {
            setBusy(false);
        }
    };

    const runEgress = async () => {
        if (!egressUrl.trim()) return;
        setBusy(true);
        try {
            const v = await api.egressCheck(egressUrl);
            setEgressVerdict(v);
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'egress check failed');
        } finally {
            setBusy(false);
        }
    };

    const allowDomain = async () => {
        if (!egressNewDomain.trim()) return;
        setBusy(true);
        try {
            await api.egressAllowDomain(egressNewDomain.trim());
            setEgressNewDomain('');
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'allow domain failed');
        } finally {
            setBusy(false);
        }
    };

    const supplyScan = async () => {
        setBusy(true);
        try {
            await api.supplyChainScan();
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'supply chain scan failed');
        } finally {
            setBusy(false);
        }
    };

    const supplyBaseline = async () => {
        setBusy(true);
        try {
            await api.supplyChainBaseline();
            await refresh();
        } catch (exc) {
            setError(exc instanceof Error ? exc.message : 'baseline update failed');
        } finally {
            setBusy(false);
        }
    };

    const overviewTiles = useMemo(() => {
        if (!overview) return [];
        const ps = overview.prompt_shield as Record<string, number>;
        const ss = overview.secret_scanner as Record<string, number>;
        const tg = overview.tool_gate as Record<string, number>;
        const eg = overview.egress_guardian as Record<string, number>;
        const bm = overview.behavior_monitor as Record<string, number>;
        const sc = overview.supply_chain_sentinel as Record<string, number>;
        return [
            { label: 'shield checked', value: ps.checked ?? 0 },
            { label: 'shield blocks', value: ps.blocked ?? 0, accent: (ps.blocked ?? 0) > 0 ? 'bad' : undefined },
            { label: 'secret scans', value: ss.scanned ?? 0 },
            { label: 'secrets found', value: ss.findings ?? 0, accent: (ss.findings ?? 0) > 0 ? 'bad' : undefined },
            { label: 'gate checks', value: tg.checks ?? 0 },
            { label: 'gate denies', value: tg.denied ?? 0, accent: (tg.denied ?? 0) > 0 ? 'warn' : undefined },
            { label: 'egress blocks', value: eg.blocked ?? 0, accent: (eg.blocked ?? 0) > 0 ? 'warn' : undefined },
            { label: 'behavior halts', value: bm.halt_violations ?? 0, accent: (bm.halt_violations ?? 0) > 0 ? 'bad' : undefined },
            { label: 'CVE total', value: sc.total_findings ?? 0, accent: (sc.total_findings ?? 0) > 0 ? 'warn' : undefined },
            { label: 'CVE new vs baseline', value: sc.new_vs_baseline ?? 0, accent: (sc.new_vs_baseline ?? 0) > 0 ? 'bad' : undefined },
        ] as { label: string; value: string | number; accent?: 'good' | 'warn' | 'bad' }[];
    }, [overview]);

    return (
        <div className="space-y-6 p-6">
            <PageHeader
                title="Security"
                description="Six defensive agents protecting the platform: prompt shield, secret scanner, tool gate, egress guardian, behavior monitor, and supply-chain sentinel. All run locally."
                meta={
                    error ? (
                        <span className="text-status-error">{error}</span>
                    ) : (
                        <span>auto-refreshes every 20s</span>
                    )
                }
                actions={
                    <Button variant="secondary" size="md" onClick={() => refresh().catch(() => undefined)}>
                        <RefreshCw className="h-4 w-4" /> Refresh
                    </Button>
                }
            />

            <PageSection title="Overview">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                    {overviewTiles.map((tile) => (
                        <StatTile key={tile.label} {...tile} />
                    ))}
                </div>
            </PageSection>

            <PageSection title="Prompt shield">
                <div className="flex flex-wrap items-center gap-2">
                    <input
                        value={shieldGuardrailModel}
                        onChange={(e) => setShieldGuardrailModel(e.target.value)}
                        placeholder="guardrail model tag (e.g. granite-guardian:8b)"
                        className="flex-1 rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                    />
                    <Button variant="secondary" size="md" disabled={busy} onClick={setGuardrail}>
                        Set guardrail model
                    </Button>
                    <label className="inline-flex items-center gap-2 text-sm">
                        <input
                            type="checkbox"
                            checked={shieldUseGuardrail}
                            onChange={(e) => setShieldUseGuardrail(e.target.checked)}
                        />
                        Use guardrail this check
                    </label>
                </div>
                <textarea
                    value={shieldText}
                    onChange={(e) => setShieldText(e.target.value)}
                    rows={4}
                    placeholder="Paste a prompt to test for injection patterns..."
                    className="mt-3 w-full rounded-md border border-surface-4 bg-surface-2 px-3 py-2 text-sm"
                />
                <div className="mt-2 flex gap-2">
                    <Button variant="subtle" size="md" disabled={busy || !shieldText.trim()} onClick={runShield}>
                        Check
                    </Button>
                </div>
                {shieldVerdict && (
                    <div className="mt-3 rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                        <div className="mb-1 font-mono text-[11px] text-text-muted">verdict</div>
                        <div className={`mb-2 text-base font-semibold ${
                            shieldVerdict.action === 'block'
                                ? 'text-status-error'
                                : shieldVerdict.action === 'flag'
                                    ? 'text-status-warning'
                                    : 'text-status-success'
                        }`}>
                            {shieldVerdict.action.toUpperCase()} ({shieldVerdict.severity})
                        </div>
                        {shieldVerdict.reasons.length > 0 && (
                            <ul className="list-disc pl-5">
                                {shieldVerdict.reasons.map((r, idx) => (
                                    <li key={idx}>{r}</li>
                                ))}
                            </ul>
                        )}
                        {shieldVerdict.pattern_matches.length > 0 && (
                            <div className="mt-2 space-y-1 font-mono text-[11px] text-text-secondary">
                                {shieldVerdict.pattern_matches.map((m, idx) => (
                                    <div key={idx}>
                                        [{m.severity}] {m.rule}
                                        {m.snippet ? ` — ${m.snippet}` : ''}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </PageSection>

            <PageSection title="Secret scanner">
                <textarea
                    value={secretText}
                    onChange={(e) => setSecretText(e.target.value)}
                    rows={6}
                    placeholder="Paste any text — code, args, output — to scan for credentials..."
                    className="w-full rounded-md border border-surface-4 bg-surface-2 px-3 py-2 text-sm"
                />
                <div className="mt-2 flex gap-2">
                    <Button variant="subtle" size="md" disabled={busy || !secretText.trim()} onClick={runSecretScan}>
                        Scan
                    </Button>
                </div>
                {secretFindings.length > 0 ? (
                    <div className="mt-3 space-y-1.5">
                        {secretFindings.map((f, idx) => (
                            <div key={idx} className="rounded-md border border-status-error/40 bg-surface-2 p-3 text-sm">
                                <div className="font-mono text-[11px] text-status-error">
                                    {f.rule} (line {f.line}) · {f.description}
                                </div>
                                <div className="mt-1 font-mono">{f.match}</div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="mt-3 text-sm text-text-muted">No findings yet.</div>
                )}
            </PageSection>

            <PageSection title="Tool gate">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div>
                        <div className="text-[11px] uppercase tracking-wide text-text-muted">Policies ({policies.length})</div>
                        <div className="mt-2 max-h-96 space-y-1 overflow-auto">
                            {policies.map((p) => (
                                <div key={p.tool} className="rounded-md border border-surface-4 bg-surface-2 p-2 text-sm">
                                    <div className="flex items-center justify-between">
                                        <span className="font-medium">{p.tool}</span>
                                        <span className="font-mono text-[11px] text-text-muted">
                                            {p.rate_limit_per_minute}/min · {p.max_arg_chars}b
                                        </span>
                                    </div>
                                    {(p.required_arg_keys.length > 0 || p.forbidden_arg_keys.length > 0) && (
                                        <div className="mt-0.5 font-mono text-[11px] text-text-muted">
                                            {p.required_arg_keys.length > 0 && <>require {p.required_arg_keys.join(', ')} </>}
                                            {p.forbidden_arg_keys.length > 0 && <>· forbid {p.forbidden_arg_keys.join(', ')}</>}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                    <div>
                        <div className="text-[11px] uppercase tracking-wide text-text-muted">Recent audit ({audit.length})</div>
                        <div className="mt-2 max-h-96 space-y-1 overflow-auto">
                            {audit.length === 0 && <div className="text-sm text-text-muted">No tool calls audited yet.</div>}
                            {audit.map((row) => (
                                <div
                                    key={row.id}
                                    className={`rounded-md border p-2 text-sm ${
                                        row.decision === 'allow'
                                            ? 'border-surface-4 bg-surface-2'
                                            : 'border-status-warning/40 bg-surface-2'
                                    }`}
                                >
                                    <div className="flex items-center justify-between">
                                        <span className="font-mono text-[11px]">
                                            {row.tool} · {row.agent_id}
                                        </span>
                                        <span className="font-mono text-[11px] text-text-muted">
                                            {row.decision} · {formatRelative(row.timestamp)}
                                        </span>
                                    </div>
                                    {row.reasons.length > 0 && (
                                        <div className="mt-1 font-mono text-[11px] text-status-warning">
                                            {row.reasons.join(' · ')}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </PageSection>

            <PageSection title="Egress guardian">
                <div className="flex flex-wrap items-center gap-2">
                    <input
                        value={egressUrl}
                        onChange={(e) => setEgressUrl(e.target.value)}
                        placeholder="https://example.com/path"
                        className="flex-1 rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                    />
                    <Button variant="subtle" size="md" disabled={busy || !egressUrl.trim()} onClick={runEgress}>
                        Check
                    </Button>
                </div>
                {egressVerdict && (
                    <div className="mt-3 rounded-md border border-surface-4 bg-surface-2 p-3 text-sm">
                        <div className={`text-base font-semibold ${egressVerdict.allowed ? 'text-status-success' : 'text-status-error'}`}>
                            {egressVerdict.allowed ? 'ALLOWED' : 'BLOCKED'} · {egressVerdict.host}
                        </div>
                        {egressVerdict.matched_rule && (
                            <div className="mt-1 font-mono text-[11px] text-text-muted">matched {egressVerdict.matched_rule}</div>
                        )}
                        {egressVerdict.reason && (
                            <div className="mt-1 font-mono text-[11px] text-status-warning">{egressVerdict.reason}</div>
                        )}
                    </div>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                    <input
                        value={egressNewDomain}
                        onChange={(e) => setEgressNewDomain(e.target.value)}
                        placeholder="add domain to allowlist (e.g. api.openai.com)"
                        className="flex-1 rounded-md border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm"
                    />
                    <Button variant="secondary" size="md" disabled={busy || !egressNewDomain.trim()} onClick={allowDomain}>
                        Allow domain
                    </Button>
                </div>
            </PageSection>

            <PageSection title="Supply chain">
                <div className="flex flex-wrap items-center gap-2">
                    <Button variant="subtle" size="md" disabled={busy} onClick={supplyScan}>
                        Run scan now
                    </Button>
                    <Button variant="secondary" size="md" disabled={busy || !supplyLatest?.findings?.length} onClick={supplyBaseline}>
                        Update baseline to current
                    </Button>
                    <span className="font-mono text-[11px] text-text-muted">
                        last scan {formatRelative(supplyLatest?.started_at ?? 0)} · duration {supplyLatest?.duration_seconds ?? 0}s
                    </span>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
                    <StatTile label="total findings" value={supplyLatest?.findings?.length ?? 0} accent={(supplyLatest?.findings?.length ?? 0) > 0 ? 'warn' : undefined} />
                    <StatTile label="new vs baseline" value={supplyDiff?.new_count ?? 0} accent={(supplyDiff?.new_count ?? 0) > 0 ? 'bad' : 'good'} />
                    <StatTile label="resolved vs baseline" value={supplyDiff?.resolved_count ?? 0} accent={(supplyDiff?.resolved_count ?? 0) > 0 ? 'good' : undefined} />
                    <StatTile label="errors" value={supplyLatest?.errors?.length ?? 0} accent={(supplyLatest?.errors?.length ?? 0) > 0 ? 'warn' : undefined} />
                </div>

                {supplyDiff && supplyDiff.new_findings.length > 0 && (
                    <div className="mt-4">
                        <div className="text-[11px] uppercase tracking-wide text-text-muted">New findings since baseline</div>
                        <div className="mt-2 max-h-96 space-y-1 overflow-auto">
                            {supplyDiff.new_findings.map((f, idx) => (
                                <div key={idx} className="rounded-md border border-status-error/40 bg-surface-2 p-3 text-sm">
                                    <div className="flex items-center justify-between">
                                        <span className="font-mono text-[11px]">
                                            {f.ecosystem}:{f.package}@{f.installed_version}
                                        </span>
                                        <span className={`font-mono text-[11px] ${f.severity === 'critical' || f.severity === 'high' ? 'text-status-error' : 'text-status-warning'}`}>
                                            {f.severity}
                                        </span>
                                    </div>
                                    <div className="mt-1 text-text-secondary">
                                        {f.cve_ids.join(', ') || f.advisory_ids.join(', ') || '—'}
                                    </div>
                                    {f.summary && <div className="mt-1 text-text-secondary">{f.summary}</div>}
                                    {f.fix_versions.length > 0 && (
                                        <div className="mt-1 font-mono text-[11px] text-status-success">
                                            fix: {f.fix_versions.join(', ')}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {(!supplyLatest?.findings || supplyLatest.findings.length === 0) && (
                    <div className="mt-3 text-sm text-text-muted">
                        No CVE scan results yet. Click "Run scan now" — pip-audit (Python) and npm audit (frontend) will run as
                        subprocesses; baseline lets you focus on new findings only.
                    </div>
                )}
            </PageSection>
        </div>
    );
}
