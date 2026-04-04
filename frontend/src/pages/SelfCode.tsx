import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import * as agentApi from '../lib/agentSpaceApi';
import { PageHeader } from '../components/PageHeader';

export default function SelfCode() {
    const [advancedMode, setAdvancedMode] = useState(false);
    const [prompt, setPrompt] = useState('');
    const [runId, setRunId] = useState('');
    const [runStatus, setRunStatus] = useState('');
    const [runs, setRuns] = useState<agentApi.AgentSpaceRunSummary[]>([]);
    const [events, setEvents] = useState<agentApi.AgentSpaceEvent[]>([]);
    const [runReviews, setRunReviews] = useState<agentApi.AgentSpaceReview[]>([]);
    const [suggestions, setSuggestions] = useState<agentApi.SelfImproveSuggestion[]>([]);
    const [autonomousNotes, setAutonomousNotes] = useState<string[]>([]);
    const [confirmedMap, setConfirmedMap] = useState<Record<string, boolean>>({});
    const [suggesting, setSuggesting] = useState(false);
    const [starting, setStarting] = useState(false);
    const [stopping, setStopping] = useState(false);
    const [applyingReviews, setApplyingReviews] = useState(false);
    const [undoingReview, setUndoingReview] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const confirmedSuggestions = useMemo(
        () => suggestions.filter((row) => Boolean(confirmedMap[row.id])).map((row) => row.text),
        [confirmedMap, suggestions],
    );
    const selectedRun = useMemo(() => runs.find((row) => row.id === runId) || null, [runs, runId]);
    const runReviewSummary = useMemo(() => {
        let fileCount = 0;
        let added = 0;
        let removed = 0;
        for (const review of runReviews) {
            const summary = review.summary;
            if (!summary) continue;
            fileCount += Number(summary.file_count || 0);
            added += Number(summary.added_lines || 0);
            removed += Number(summary.removed_lines || 0);
        }
        return { fileCount, added, removed };
    }, [runReviews]);
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

    const suggestImprovements = useCallback(async () => {
        setMessage('');
        setError('');
        if (!prompt.trim()) {
            setError('Enter a self-improvement prompt first.');
            return;
        }
        setSuggesting(true);
        try {
            const resp = await agentApi.suggestSelfImprove({
                prompt: prompt.trim(),
                max_suggestions: 8,
            });
            setSuggestions(resp.suggestions || []);
            setAutonomousNotes(resp.autonomous_notes || []);
            setConfirmedMap({});
            setMessage(`Generated ${resp.suggestions.length} suggestions. Confirm what to run.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to generate suggestions.');
        } finally {
            setSuggesting(false);
        }
    }, [prompt]);

    const toggleConfirmed = useCallback((id: string) => {
        setConfirmedMap((prev) => ({ ...prev, [id]: !prev[id] }));
    }, []);

    const confirmAll = useCallback(() => {
        const next: Record<string, boolean> = {};
        for (const row of suggestions) {
            next[row.id] = true;
        }
        setConfirmedMap(next);
    }, [suggestions]);

    const runSelfImprove = useCallback(async () => {
        setMessage('');
        setError('');
        if (!prompt.trim()) {
            setError('Enter a self-improvement prompt first.');
            return;
        }
        if (confirmedSuggestions.length === 0) {
            setError('Confirm at least one suggested improvement before running.');
            return;
        }
        setStarting(true);
        setEvents([]);
        try {
            const run = await agentApi.runSelfImprove({
                prompt: prompt.trim(),
                confirmed_suggestions: confirmedSuggestions,
            });
            setRunId(run.id);
            setRunStatus(run.status || 'queued');
            setMessage(`Self-improvement run queued: ${run.id}`);
            await refreshRuns();
            await refreshRunReviews();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start self-improvement run.');
        } finally {
            setStarting(false);
        }
    }, [confirmedSuggestions, prompt, refreshRunReviews, refreshRuns]);

    const runSelfImproveDirect = useCallback(async () => {
        setMessage('');
        setError('');
        if (!prompt.trim()) {
            setError('Enter a self-improvement prompt first.');
            return;
        }
        setStarting(true);
        setEvents([]);
        try {
            const run = await agentApi.runSelfImprove({
                prompt: prompt.trim(),
                confirmed_suggestions: [prompt.trim()],
                direct_prompt_mode: true,
            });
            setRunId(run.id);
            setRunStatus(run.status || 'queued');
            setMessage(`Direct self-improvement run queued: ${run.id}`);
            await refreshRuns();
            await refreshRunReviews();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to start direct self-improvement run.');
        } finally {
            setStarting(false);
        }
    }, [prompt, refreshRunReviews, refreshRuns]);

    const stopRun = useCallback(async () => {
        if (!runId) return;
        setMessage('');
        setError('');
        setStopping(true);
        try {
            await agentApi.stopRun(runId, 'Stopped from Improve App page.');
            setRunStatus('stopped');
            setMessage(`Stop requested for run ${runId}.`);
            await refreshRuns();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to stop run.');
        } finally {
            setStopping(false);
        }
    }, [refreshRuns, runId]);

    const applyAllRunReviews = useCallback(async () => {
        if (!runId) return;
        setMessage('');
        setError('');
        setApplyingReviews(true);
        try {
            const reviews = await agentApi.listReviews(500);
            const targets = reviews.filter((review) => review.run_id === runId && review.status !== 'applied' && review.status !== 'rejected');
            if (targets.length === 0) {
                setMessage('No pending/approved reviews found for this run.');
                return;
            }
            let applied = 0;
            for (const review of targets) {
                if (review.status === 'pending') {
                    await agentApi.approveReview(review.id);
                }
                await agentApi.applyReview(review.id);
                applied += 1;
            }
            await refreshRunReviews();
            await refreshRuns();
            setMessage(`Applied ${applied} review diff(s) for run ${runId.slice(0, 8)}.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to apply run reviews.');
        } finally {
            setApplyingReviews(false);
        }
    }, [refreshRunReviews, refreshRuns, runId]);

    const undoLastAppliedReview = useCallback(async () => {
        if (!latestAppliedReview) return;
        setMessage('');
        setError('');
        setUndoingReview(true);
        try {
            await agentApi.undoReview(latestAppliedReview.id);
            await refreshRunReviews();
            await refreshRuns();
            setMessage(`Undid review ${latestAppliedReview.id.slice(0, 8)}.`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to undo review.');
        } finally {
            setUndoingReview(false);
        }
    }, [latestAppliedReview, refreshRunReviews, refreshRuns]);

    return (
        <div className="h-full overflow-auto p-6 md:p-10">
            <div className="mx-auto w-full max-w-[min(112rem,calc(100%-2rem))] space-y-6">
                <PageHeader
                    title="Improve jimAI"
                    description="Self-improve requires your prompt. You can run directly from prompt, or generate specific suggestions and confirm them first."
                    actions={
                        <button
                            type="button"
                            onClick={() => setAdvancedMode((prev) => !prev)}
                            className={`px-2.5 py-1.5 rounded-btn border text-xs ${
                                advancedMode
                                    ? 'border-accent/40 text-accent bg-accent/10'
                                    : 'border-surface-4 text-text-secondary hover:bg-surface-2'
                            }`}
                        >
                            {advancedMode ? 'Advanced: ON' : 'Simple: ON'}
                        </button>
                    }
                />
                <section className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                    <label className="block text-xs font-medium text-text-primary">Self-Improve Prompt (Required / Editable)</label>
                    <textarea
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
                        placeholder="Example: Improve build reliability, simplify core flows, and harden review/apply behavior."
                        className="mt-2 w-full min-h-[110px] rounded-btn border border-surface-4 bg-surface-0 px-3 py-2 text-sm text-text-primary outline-none focus:border-white/40"
                    />
                    <div className="mt-4 flex flex-wrap gap-2">
                        <button
                            type="button"
                            onClick={() => suggestImprovements().catch(() => {})}
                            disabled={suggesting || !prompt.trim()}
                            className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary disabled:opacity-40"
                        >
                            {suggesting ? 'Generating...' : 'Generate Suggestions'}
                        </button>
                        <button
                            type="button"
                            onClick={() => confirmAll()}
                            disabled={suggestions.length === 0}
                            className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary disabled:opacity-40"
                        >
                            Confirm All
                        </button>
                        <button
                            type="button"
                            onClick={() => runSelfImprove().catch(() => {})}
                            disabled={starting || !prompt.trim() || confirmedSuggestions.length === 0}
                            className="px-4 py-2 rounded-btn border border-accent/40 text-accent text-sm disabled:opacity-40"
                        >
                            {starting ? 'Starting...' : 'Run Self-Improve'}
                        </button>
                        <button
                            type="button"
                            onClick={() => stopRun().catch(() => {})}
                            disabled={!runId || stopping}
                            className="px-4 py-2 rounded-btn border border-accent-red/40 text-accent-red text-sm disabled:opacity-40"
                        >
                            {stopping ? 'Stopping...' : 'Stop Current'}
                        </button>
                        <Link
                            to="/workflow"
                            className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary hover:bg-surface-2"
                        >
                            Open Review
                        </Link>
                        {advancedMode && (
                            <>
                                <button
                                    type="button"
                                    onClick={() => runSelfImproveDirect().catch(() => {})}
                                    disabled={starting || !prompt.trim()}
                                    className="px-4 py-2 rounded-btn border border-surface-4 text-sm text-text-primary disabled:opacity-40"
                                >
                                    {starting ? 'Starting...' : 'Run Prompt Directly'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => applyAllRunReviews().catch(() => {})}
                                    disabled={!runId || applyingReviews || runReviews.length === 0}
                                    className="px-4 py-2 rounded-btn border border-accent-green/40 text-accent-green text-sm disabled:opacity-40"
                                >
                                    {applyingReviews ? 'Applying...' : 'Approve + Apply Run Diffs'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => undoLastAppliedReview().catch(() => {})}
                                    disabled={!latestAppliedReview || undoingReview}
                                    className="px-4 py-2 rounded-btn border border-accent-amber/50 text-accent-amber text-sm disabled:opacity-40"
                                >
                                    {undoingReview ? 'Undoing...' : 'Undo Last Applied Diff'}
                                </button>
                            </>
                        )}
                    </div>
                    {!advancedMode && (
                        <p className="mt-2 text-[11px] text-text-muted">
                            Simple mode hides direct-run/apply-all/undo controls.
                        </p>
                    )}
                    <p className="mt-3 text-xs text-text-secondary">confirmed suggestions: {confirmedSuggestions.length}</p>
                    <p className="mt-2 text-xs text-text-secondary">
                        current run: {runId || 'none'} {runStatus ? `-> ${runStatus}` : ''}
                    </p>
                    {selectedRun?.completion_summary?.text && (
                        <div className="mt-3 rounded-btn border border-surface-4 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Latest Summary</p>
                            <p className="text-xs text-text-primary mt-1">{selectedRun.completion_summary.text}</p>
                        </div>
                    )}
                </section>

                <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                    <h2 className="text-sm font-semibold text-text-primary">Suggested Improvements (Confirm Before Run)</h2>
                    <div className="mt-3 space-y-2">
                        {suggestions.length === 0 && (
                            <p className="text-xs text-text-secondary">No suggestions yet. Generate suggestions from your prompt first.</p>
                        )}
                        {suggestions.map((row) => (
                            <label key={row.id} className="flex items-start gap-2 rounded-btn border border-surface-4 bg-surface-0 p-3">
                                <input
                                    type="checkbox"
                                    checked={Boolean(confirmedMap[row.id])}
                                    onChange={() => toggleConfirmed(row.id)}
                                    className="mt-1"
                                />
                                <span className="text-xs text-text-primary">{row.text}</span>
                            </label>
                        ))}
                    </div>
                    {autonomousNotes.length > 0 && (
                        <div className="mt-4 space-y-1">
                            <p className="text-xs font-medium text-text-primary">Autonomous Notes</p>
                            {autonomousNotes.map((note, idx) => (
                                <p key={`${idx}-${note}`} className="text-xs text-text-secondary">
                                    - {note}
                                </p>
                            ))}
                        </div>
                    )}
                </section>

                <section className={`grid grid-cols-1 ${advancedMode ? 'lg:grid-cols-[320px_minmax(0,1fr)]' : ''} gap-4`}>
                    {advancedMode && (
                        <div className="rounded-card border border-surface-4 bg-surface-1 p-4">
                            <h2 className="text-sm font-semibold text-text-primary">Recent Runs</h2>
                            <div className="mt-3 max-h-[420px] overflow-auto space-y-2">
                                {runs.length === 0 && <p className="text-xs text-text-secondary">No runs yet.</p>}
                                {runs.map((run) => (
                                    <button
                                        key={run.id}
                                        type="button"
                                        onClick={() => {
                                            setRunId(run.id);
                                            setRunStatus(run.status);
                                            setEvents([]);
                                        }}
                                        className={`w-full text-left rounded-btn border p-3 ${
                                            runId === run.id ? 'border-accent/50 bg-surface-2' : 'border-surface-4 bg-surface-0'
                                        }`}
                                    >
                                        <p className="text-xs text-text-primary truncate">{run.objective}</p>
                                        <p className="text-[11px] text-text-secondary mt-1">
                                            {`${run.status} -> actions ${run.action_count}`}
                                        </p>
                                        {run.completion_summary?.text && (
                                            <p className="text-[11px] text-text-muted mt-1 line-clamp-2">{run.completion_summary.text}</p>
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="rounded-card border border-surface-4 bg-surface-1 p-4">
                        <h2 className="text-sm font-semibold text-text-primary">Live Events</h2>
                        <div className="mt-3 max-h-[420px] overflow-auto space-y-2">
                            {events.length === 0 && <p className="text-xs text-text-secondary">No events yet.</p>}
                            {events.map((event, idx) => (
                                <div key={`${idx}-${event.type}`} className="rounded-btn border border-surface-4 bg-surface-0 p-2">
                                    <p className="text-[11px] text-text-primary">{event.type}</p>
                                    <p className="text-[11px] text-text-secondary">{String(event.message || '')}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                {advancedMode && (
                    <section className="rounded-card border border-surface-4 bg-surface-1 p-4">
                        <h2 className="text-sm font-semibold text-text-primary">Review Diffs From This Run</h2>
                        {runReviews.length > 0 && (
                            <p className="mt-2 text-xs text-text-secondary">
                                total reviews: {runReviews.length} • files: {runReviewSummary.fileCount} • +{runReviewSummary.added} / -{runReviewSummary.removed}
                            </p>
                        )}
                        {latestAppliedReview && (
                            <p className="mt-1 text-xs text-text-secondary">
                                latest applied review: {latestAppliedReview.id.slice(0, 8)}
                            </p>
                        )}
                        <div className="mt-3 space-y-2">
                            {runReviews.length === 0 && <p className="text-xs text-text-secondary">No review diffs yet for current run.</p>}
                            {runReviews.map((review) => (
                                <div key={review.id} className="rounded-btn border border-surface-4 bg-surface-0 p-3">
                                    <div className="flex items-center justify-between gap-2">
                                        <p className="text-xs text-text-primary truncate">{review.objective}</p>
                                        <span className="text-[11px] text-text-secondary">{review.status}</span>
                                    </div>
                                    <p className="text-[11px] text-text-muted mt-1">review: {review.id}</p>
                                    {review.summary && (
                                        <p className="text-[11px] text-text-secondary mt-1">
                                            files {review.summary.file_count} • +{review.summary.added_lines} / -{review.summary.removed_lines}
                                        </p>
                                    )}
                                </div>
                            ))}
                        </div>
                    </section>
                )}

                {message && <p className="text-sm text-accent-green">{message}</p>}
                {error && <p className="text-sm text-accent-red">{error}</p>}
            </div>
        </div>
    );
}
