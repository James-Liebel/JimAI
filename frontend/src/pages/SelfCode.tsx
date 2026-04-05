import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { Link } from 'react-router-dom';
import * as agentApi from '../lib/agentSpaceApi';
import * as selfCodeSession from '../lib/selfCodeSession';
import { PageHeader } from '../components/PageHeader';

function summarizeAction(action: Record<string, unknown>): string {
    const t = String(action.type ?? action.action ?? 'action');
    const bits: string[] = [t];
    for (const key of ['command', 'path', 'to', 'channel', 'focus', 'url'] as const) {
        const v = action[key];
        if (v == null) continue;
        const s = String(v).replace(/\s+/g, ' ').trim();
        if (!s) continue;
        bits.push(`${key}: ${s.length > 100 ? `${s.slice(0, 97)}…` : s}`);
        if (bits.length >= 3) break;
    }
    return bits.join(' · ');
}

function actionSucceeded(result: Record<string, unknown> | undefined): boolean {
    if (!result || typeof result !== 'object') return true;
    if ('success' in result && result.success === false) return false;
    return true;
}

function isRunInProgress(status: string) {
    const s = (status || '').toLowerCase();
    return s === 'running' || s === 'queued';
}

export default function SelfCode() {
    const [improvePrompt, setImprovePrompt] = useState(() => selfCodeSession.loadImprovePrompt());
    const [runId, setRunId] = useState(() => selfCodeSession.loadRunId());
    const [runStatus, setRunStatus] = useState('');
    const [runs, setRuns] = useState<agentApi.AgentSpaceRunSummary[]>([]);
    const [events, setEvents] = useState<agentApi.AgentSpaceEvent[]>([]);
    const [runReviews, setRunReviews] = useState<agentApi.AgentSpaceReview[]>([]);

    const [starting, setStarting] = useState(false);
    const [stopping, setStopping] = useState(false);
    const [undoingReview, setUndoingReview] = useState(false);

    const analyzerSnap = useSyncExternalStore(
        selfCodeSession.subscribeSelfAnalyze,
        selfCodeSession.getSelfAnalyzeSnapshot,
        selfCodeSession.getSelfAnalyzeSnapshot,
    );
    const strengthenBusy = useSyncExternalStore(
        selfCodeSession.subscribeStrengthen,
        selfCodeSession.getStrengthenBusySnapshot,
        selfCodeSession.getStrengthenBusySnapshot,
    );
    const canRevertStrengthen = useSyncExternalStore(
        selfCodeSession.subscribeStrengthen,
        selfCodeSession.hasRevertStrengthenSnapshot,
        selfCodeSession.hasRevertStrengthenSnapshot,
    );

    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const [runActions, setRunActions] = useState<agentApi.ActionLogEntry[]>([]);
    const [runActionsError, setRunActionsError] = useState('');

    const waitActive = strengthenBusy || analyzerSnap.analyzing || starting;
    const [elapsedSec, setElapsedSec] = useState(0);

    const selectedRun = useMemo(() => runs.find((row) => row.id === runId) || null, [runs, runId]);
    const runBusy = isRunInProgress(runStatus);
    const latestAppliedReview = useMemo(
        () => runReviews.find((review) => review.status === 'applied' && Boolean(review.snapshot_id)) || null,
        [runReviews],
    );

    const refreshRuns = useCallback(async () => {
        const rows = await agentApi.listRuns(80);
        setRuns(rows);
        if (runId) {
            const current = rows.find((row) => row.id === runId);
            if (current) setRunStatus(current.status);
        }
    }, [runId]);

    const refreshRunReviews = useCallback(async () => {
        if (!runId) {
            setRunReviews([]);
            return;
        }
        const reviews = await agentApi.listReviews(300);
        setRunReviews(reviews.filter((review) => review.run_id === runId));
    }, [runId]);

    useEffect(() => {
        refreshRuns().catch(() => {});
        const id = window.setInterval(() => refreshRuns().catch(() => {}), 2500);
        return () => window.clearInterval(id);
    }, [refreshRuns]);

    useEffect(() => {
        if (!runId) {
            setEvents([]);
            return;
        }
        const unsubscribe = agentApi.subscribeRunEvents(
            runId,
            (event) => setEvents((prev) => [...prev.slice(-399), event]),
            () => {},
        );
        return unsubscribe;
    }, [runId]);

    useEffect(() => {
        refreshRunReviews().catch(() => {});
        const id = window.setInterval(() => refreshRunReviews().catch(() => {}), 3000);
        return () => window.clearInterval(id);
    }, [refreshRunReviews]);

    useEffect(() => {
        if (!waitActive) {
            setElapsedSec(0);
            return;
        }
        const t0 = Date.now();
        setElapsedSec(0);
        const id = window.setInterval(() => setElapsedSec(Math.floor((Date.now() - t0) / 1000)), 1000);
        return () => window.clearInterval(id);
    }, [waitActive]);

    const refreshRunActions = useCallback(async () => {
        if (!runId) {
            setRunActions([]);
            setRunActionsError('');
            return;
        }
        try {
            const rows = await agentApi.getActionLogs(120, runId);
            setRunActions(rows);
            setRunActionsError('');
        } catch (err) {
            setRunActionsError(err instanceof Error ? err.message : 'Failed to load action log.');
        }
    }, [runId]);

    useEffect(() => {
        refreshRunActions().catch(() => {});
        const id = window.setInterval(() => refreshRunActions().catch(() => {}), 2000);
        return () => window.clearInterval(id);
    }, [refreshRunActions]);

    useEffect(() => {
        const t = window.setTimeout(() => selfCodeSession.persistImprovePrompt(improvePrompt), 400);
        return () => window.clearTimeout(t);
    }, [improvePrompt]);

    useEffect(() => {
        selfCodeSession.persistRunId(runId);
    }, [runId]);

    useEffect(() => {
        const sync = () => {
            const next = selfCodeSession.consumePendingStrengthenPrompt();
            if (next != null) {
                setImprovePrompt(next);
                setMessage('Prompt strengthened. Use “Revert strengthen” to restore the previous text.');
                setError('');
            }
            const err = selfCodeSession.consumePendingStrengthenError();
            if (err) {
                setError(err);
            }
        };
        sync();
        const unsub = selfCodeSession.subscribeStrengthen(sync);
        return () => unsub();
    }, []);

    const strengthenPrompt = useCallback(() => {
        setMessage('');
        setError('');
        const raw = improvePrompt.trim();
        if (raw.length < 5) {
            setError('Enter at least a few words so the local model can strengthen your prompt.');
            return;
        }
        selfCodeSession.startStrengthenSession(raw, improvePrompt);
    }, [improvePrompt]);

    const revertStrengthen = useCallback(() => {
        selfCodeSession.revertStrengthenSession(setImprovePrompt);
        setMessage('Restored text from before strengthen.');
        setError('');
    }, []);

    const runImprovement = useCallback(async () => {
        setMessage('');
        setError('');
        const raw = improvePrompt.trim();
        if (raw.length < 5) {
            setError('Enter a prompt (at least 5 characters) to run an improvement.');
            return;
        }
        setStarting(true);
        setEvents([]);
        try {
            const run = await agentApi.runSelfImprove({
                prompt: raw,
                confirmed_suggestions: [raw],
                direct_prompt_mode: true,
            });
            setRunId(run.id);
            selfCodeSession.persistRunId(run.id);
            setRunStatus(run.status || 'queued');
            setMessage(
                `Improvement run started: ${run.id.slice(0, 8)}… — runs keep going if you switch pages; reopen SelfCode to follow progress.`,
            );
            await refreshRuns();
            await refreshRunReviews();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start improvement run.');
        } finally {
            setStarting(false);
        }
    }, [improvePrompt, refreshRunReviews, refreshRuns]);

    const stopRun = useCallback(async () => {
        if (!runId) return;
        setMessage('');
        setError('');
        setStopping(true);
        try {
            await agentApi.stopRun(runId, 'Stopped from Improve App page.');
            setRunStatus('stopped');
            setMessage(`Stop requested for run ${runId.slice(0, 8)}…`);
            await refreshRuns();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to stop run.');
        } finally {
            setStopping(false);
        }
    }, [refreshRuns, runId]);

    const stopSelfAnalyzer = useCallback(() => {
        selfCodeSession.stopSelfAnalyzeSession();
    }, []);

    const analyzeApp = useCallback(() => {
        setError('');
        selfCodeSession.startSelfAnalyzeSession();
    }, []);

    const undoLastAppliedReview = useCallback(async () => {
        if (!latestAppliedReview) return;
        setMessage('');
        setError('');
        setUndoingReview(true);
        try {
            await agentApi.undoReview(latestAppliedReview.id);
            await refreshRunReviews();
            await refreshRuns();
            setMessage(`Reverted last applied change (review ${latestAppliedReview.id.slice(0, 8)}…).`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to revert.');
        } finally {
            setUndoingReview(false);
        }
    }, [latestAppliedReview, refreshRunReviews, refreshRuns]);

    const copyText = useCallback(async (label: string, text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setMessage(`Copied ${label}.`);
            setError('');
        } catch {
            setError('Could not copy to clipboard.');
        }
    }, []);

    const insertIntoPrompt = useCallback((text: string) => {
        const t = text.trim();
        if (!t) return;
        setImprovePrompt((prev) => (prev.trim() ? `${prev.trim()}\n\n${t}` : t));
        setMessage('Inserted into your prompt — edit or run when ready.');
        setError('');
    }, []);

    const analysisCopyAll = useMemo(() => {
        const lines = analyzerSnap.suggestions.map((s) => s.text.trim()).filter(Boolean);
        const notes = analyzerSnap.notes.map((n) => n.trim()).filter(Boolean);
        const parts: string[] = [];
        if (notes.length) parts.push(notes.join('\n'));
        if (lines.length) parts.push(lines.map((l, i) => `${i + 1}. ${l}`).join('\n\n'));
        return parts.join('\n\n');
    }, [analyzerSnap.notes, analyzerSnap.suggestions]);

    return (
        <div className="h-full overflow-auto p-6 md:p-8">
            <div className="mx-auto w-full max-w-[min(56rem,calc(100%-2rem))] space-y-5">
                <PageHeader
                    title="Improve jimAI"
                    description="Strengthen, self-analyzer, and improvement runs keep working if you switch pages (same browser tab). Prompt and last selected run are restored when you come back."
                    actions={
                        <Link
                            to="/workflow"
                            className="rounded-btn border border-surface-4 px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary"
                        >
                            JimAI review
                        </Link>
                    }
                />

                {waitActive && (
                    <div className="rounded-card border border-accent/25 bg-accent/8 px-4 py-3 text-sm text-text-primary">
                        <p className="font-medium text-accent">Waiting on the server…</p>
                        <p className="mt-1 text-xs text-text-muted">
                            Elapsed {elapsedSec}s — local model calls can take several minutes (cold start, large prompts).
                            If nothing changes here, check the backend terminal and Ollama.
                        </p>
                    </div>
                )}

                {/* 1 — Prompt */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                    <h2 className="mb-1 text-sm font-semibold text-text-primary">Your prompt</h2>
                    <p className="mb-3 text-xs text-text-muted">
                        Describe what you want improved. Optional: let the local model tighten the wording before you run.
                    </p>
                    <textarea
                        value={improvePrompt}
                        onChange={(e) => setImprovePrompt(e.target.value)}
                        placeholder="Example: Harden the self-improve flow, simplify SelfCode UX, and add clearer stop/revert behavior."
                        disabled={starting}
                        className="w-full min-h-[128px] resize-y rounded-btn border border-surface-4 bg-surface-0 px-3 py-2.5 text-sm text-text-primary leading-relaxed disabled:opacity-50"
                    />
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            onClick={strengthenPrompt}
                            disabled={strengthenBusy || starting || !improvePrompt.trim()}
                            className="rounded-btn border border-surface-4 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary disabled:opacity-40"
                        >
                            {strengthenBusy ? 'Strengthening…' : 'Strengthen with local model'}
                        </button>
                        <button
                            type="button"
                            onClick={revertStrengthen}
                            disabled={!canRevertStrengthen}
                            className="rounded-btn border border-surface-4 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-3 hover:text-text-primary disabled:opacity-40"
                        >
                            Revert strengthen
                        </button>
                    </div>
                </section>

                {/* 2 — Run */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                    <h2 className="mb-1 text-sm font-semibold text-text-primary">Run improvement</h2>
                    <p className="mb-3 text-xs text-text-muted">
                        Uses whatever is in the box above — with or without strengthen. You can edit the prompt while a run is active and start another run; use Stop for the run selected below.
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            onClick={() => runImprovement().catch(() => {})}
                            disabled={starting || !improvePrompt.trim()}
                            className="rounded-btn bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
                        >
                            {starting ? 'Starting…' : 'Run improvement'}
                        </button>
                        <button
                            type="button"
                            onClick={() => stopRun().catch(() => {})}
                            disabled={!runId || stopping}
                            className="rounded-btn border border-accent-red/35 px-4 py-2 text-sm font-medium text-accent-red transition-colors hover:bg-accent-red/10 disabled:opacity-40"
                        >
                            {stopping ? 'Stopping…' : 'Stop current run'}
                        </button>
                        <button
                            type="button"
                            onClick={() => undoLastAppliedReview().catch(() => {})}
                            disabled={!latestAppliedReview || undoingReview}
                            className="rounded-btn border border-accent-amber/40 px-4 py-2 text-sm font-medium text-accent-amber transition-colors hover:bg-accent-amber/10 disabled:opacity-40"
                        >
                            {undoingReview ? 'Reverting…' : 'Revert last applied change'}
                        </button>
                    </div>
                    <div className="mt-4 space-y-1 border-t border-surface-5 pt-3 font-mono text-[11px] text-text-muted">
                        <p>
                            active run:{' '}
                            <span className="text-text-secondary">{runId ? `${runId.slice(0, 12)}…` : 'none'}</span>
                            {runStatus && (
                                <span className="ml-2">
                                    → <span className="text-text-secondary">{runStatus}</span>
                                </span>
                            )}
                        </p>
                        {runBusy && (
                            <p className="text-accent-amber">Run in progress — you can still edit the prompt or start an additional run.</p>
                        )}
                    </div>
                    {selectedRun?.completion_summary?.text && (
                        <div className="mt-3 rounded-btn border border-surface-4 bg-surface-0 p-3">
                            <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Summary</p>
                            <p className="text-xs leading-relaxed text-text-primary">{selectedRun.completion_summary.text}</p>
                        </div>
                    )}
                </section>

                {/* Actions for selected run */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                    <h2 className="mb-1 text-sm font-semibold text-text-primary">Agent actions</h2>
                    <p className="mb-3 text-xs text-text-muted">
                        Steps the orchestrator recorded for the selected run (updates every few seconds). If the list grows,
                        the run is making progress; if it stalls for a long time, check logs or stop and adjust your prompt.
                    </p>
                    {!runId ? (
                        <p className="text-xs text-text-muted">Start a run or pick one under “Live log & recent runs” to see actions.</p>
                    ) : runActionsError ? (
                        <p className="text-xs text-accent-red">{runActionsError}</p>
                    ) : runActions.length === 0 ? (
                        <p className="text-xs text-text-muted">
                            No actions logged for this run yet — they appear once the agent begins work.
                        </p>
                    ) : (
                        <div className="max-h-[min(24rem,50vh)] overflow-auto rounded-btn border border-surface-4 bg-surface-0">
                            <table className="w-full border-collapse text-left text-[11px]">
                                <thead className="sticky top-0 z-[1] border-b border-surface-4 bg-surface-2">
                                    <tr>
                                        <th className="px-2 py-1.5 font-medium text-text-muted">#</th>
                                        <th className="px-2 py-1.5 font-medium text-text-muted">Time</th>
                                        <th className="px-2 py-1.5 font-medium text-text-muted">Agent</th>
                                        <th className="px-2 py-1.5 font-medium text-text-muted">Action</th>
                                        <th className="px-2 py-1.5 font-medium text-text-muted">Result</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {runActions.map((row, idx) => {
                                        const ok = actionSucceeded(row.result);
                                        const errMsg =
                                            !ok && row.result && typeof row.result === 'object'
                                                ? String(
                                                      (row.result as { error?: string; message?: string }).error ||
                                                          (row.result as { message?: string }).message ||
                                                          '',
                                                  )
                                                : '';
                                        return (
                                            <tr key={`${row.ts}-${idx}`} className="border-b border-surface-5 align-top">
                                                <td className="px-2 py-1.5 font-mono text-text-muted">{idx + 1}</td>
                                                <td className="whitespace-nowrap px-2 py-1.5 font-mono text-text-muted">
                                                    {typeof row.ts === 'number'
                                                        ? new Date(row.ts * 1000).toLocaleTimeString()
                                                        : '—'}
                                                </td>
                                                <td className="max-w-[6rem] truncate px-2 py-1.5 font-mono text-text-secondary">
                                                    {row.agent_id || '—'}
                                                </td>
                                                <td className="px-2 py-1.5 text-text-primary">{summarizeAction(row.action)}</td>
                                                <td className="px-2 py-1.5">
                                                    <span className={ok ? 'text-accent-green' : 'text-accent-red'}>
                                                        {ok ? 'ok' : 'fail'}
                                                    </span>
                                                    {errMsg ? (
                                                        <span className="mt-0.5 block text-[10px] text-accent-red">{errMsg}</span>
                                                    ) : null}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </section>

                {/* 3 — App suggests */}
                <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                    <h2 className="mb-1 text-sm font-semibold text-text-primary">Ideas from the app</h2>
                    <p className="mb-3 text-xs text-text-muted">
                        Streams in the background: you can leave this page and return to see progress. Stop anytime; suggestions appear after a full parse.
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            onClick={analyzeApp}
                            disabled={analyzerSnap.analyzing}
                            className="rounded-btn border border-accent/35 bg-accent/10 px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/15 disabled:opacity-40"
                        >
                            {analyzerSnap.analyzing ? 'Analyzing…' : 'Suggest changes from the codebase'}
                        </button>
                        <button
                            type="button"
                            onClick={stopSelfAnalyzer}
                            disabled={!analyzerSnap.analyzing}
                            className="rounded-btn border border-accent-red/35 px-4 py-2 text-sm font-medium text-accent-red transition-colors hover:bg-accent-red/10 disabled:opacity-40"
                        >
                            Stop self-analyzer
                        </button>
                    </div>
                    {analyzerSnap.model && (
                        <p className="mt-2 font-mono text-[10px] text-text-muted">model: {analyzerSnap.model}</p>
                    )}
                    {(analyzerSnap.message || analyzerSnap.error) && (
                        <p
                            className={`mt-2 text-xs ${analyzerSnap.error ? 'text-accent-red' : 'font-medium text-accent-green'}`}
                        >
                            {analyzerSnap.error || analyzerSnap.message}
                        </p>
                    )}
                    {(analyzerSnap.analyzing ||
                        analyzerSnap.activity.length > 0 ||
                        analyzerSnap.streamText.length > 0) && (
                        <div className="mt-4 space-y-3 rounded-btn border border-surface-4 bg-surface-0 p-3">
                            {analyzerSnap.activity.length > 0 && (
                                <div>
                                    <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                                        Analyzer activity
                                    </p>
                                    <ol className="max-h-36 list-decimal space-y-0.5 overflow-auto pl-4 text-[11px] text-text-secondary">
                                        {analyzerSnap.activity.map((line, i) => (
                                            <li key={`${i}-${line.slice(0, 24)}`} className="font-mono">
                                                {line}
                                            </li>
                                        ))}
                                    </ol>
                                </div>
                            )}
                            {analyzerSnap.streamText.length > 0 && (
                                <div>
                                    <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">
                                        Live model output (raw JSON text)
                                    </p>
                                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-btn border border-surface-4 bg-surface-1 p-2 font-mono text-[10px] leading-relaxed text-text-secondary">
                                        {analyzerSnap.streamText}
                                    </pre>
                                </div>
                            )}
                        </div>
                    )}
                    <div className="mt-4 space-y-2">
                        {analyzerSnap.notes.length > 0 && (
                            <div className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                                <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Notes</p>
                                <ul className="list-inside list-disc space-y-1 text-xs text-text-secondary">
                                    {analyzerSnap.notes.map((note, i) => (
                                        <li key={`${i}-${note.slice(0, 24)}`}>{note}</li>
                                    ))}
                                </ul>
                                <button
                                    type="button"
                                    onClick={() => copyText('notes', analyzerSnap.notes.join('\n'))}
                                    className="mt-2 text-xs font-medium text-accent hover:underline"
                                >
                                    Copy notes
                                </button>
                            </div>
                        )}
                        {analyzerSnap.suggestions.length === 0 ? (
                            <p className="py-6 text-center text-xs text-text-muted">
                                No suggestions yet — run “Suggest changes from the codebase”.
                            </p>
                        ) : (
                            <>
                                <div className="flex flex-wrap gap-2">
                                    <button
                                        type="button"
                                        onClick={() => copyText('all suggestions', analysisCopyAll)}
                                        className="rounded-btn border border-surface-4 px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-3"
                                    >
                                        Copy all
                                    </button>
                                </div>
                                <ul className="space-y-2">
                                    {analyzerSnap.suggestions.map((row) => (
                                        <li
                                            key={row.id}
                                            className="flex flex-col gap-2 rounded-btn border border-surface-4 bg-surface-0 p-3 sm:flex-row sm:items-start sm:justify-between"
                                        >
                                            <p className="min-w-0 flex-1 text-xs leading-relaxed text-text-primary">{row.text}</p>
                                            <div className="flex shrink-0 flex-wrap gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => copyText('suggestion', row.text)}
                                                    className="rounded-btn border border-surface-4 px-2.5 py-1 text-[11px] font-medium text-text-secondary hover:bg-surface-3"
                                                >
                                                    Copy
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => insertIntoPrompt(row.text)}
                                                    className="rounded-btn border border-accent/30 px-2.5 py-1 text-[11px] font-medium text-accent hover:bg-accent/10"
                                                >
                                                    Insert into prompt
                                                </button>
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            </>
                        )}
                    </div>
                </section>

                <details className="rounded-card border border-surface-4 bg-surface-1 p-4">
                    <summary className="cursor-pointer text-xs font-medium text-text-secondary">Live log & recent runs</summary>
                    <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
                        <div>
                            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Recent runs</p>
                            <div className="max-h-[280px] space-y-1.5 overflow-auto">
                                {runs.length === 0 && <p className="text-xs text-text-muted">No runs yet.</p>}
                                {runs.map((run) => (
                                    <button
                                        key={run.id}
                                        type="button"
                                        onClick={() => {
                                            setRunId(run.id);
                                            setRunStatus(run.status);
                                            setEvents([]);
                                        }}
                                        className={`w-full rounded-btn border p-2.5 text-left transition-colors ${
                                            runId === run.id
                                                ? 'border-accent/40 bg-accent/8'
                                                : 'border-surface-4 bg-surface-0 hover:border-surface-3'
                                        }`}
                                    >
                                        <p className="truncate text-[11px] font-medium text-text-primary">{run.objective}</p>
                                        <p className="mt-0.5 font-mono text-[10px] text-text-muted">
                                            {run.status} · {run.action_count} actions
                                        </p>
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div>
                            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Events (selected run)</p>
                            <div className="max-h-[280px] space-y-1.5 overflow-auto">
                                {events.length === 0 ? (
                                    <p className="text-xs text-text-muted">Select a run or start one to see events.</p>
                                ) : (
                                    events.map((event, idx) => (
                                        <div key={`${idx}-${event.type}`} className="rounded-btn border border-surface-4 bg-surface-0 p-2">
                                            <p className="font-mono text-[10px] font-medium text-text-secondary">{event.type}</p>
                                            {event.message && (
                                                <p className="mt-0.5 text-[10px] text-text-muted">{String(event.message)}</p>
                                            )}
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                </details>

                {message && <p className="text-sm font-medium text-accent-green">{message}</p>}
                {error && <p className="text-sm text-accent-red">{error}</p>}
            </div>
        </div>
    );
}
