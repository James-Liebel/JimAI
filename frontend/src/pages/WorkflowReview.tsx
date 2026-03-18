import { useCallback, useEffect, useMemo, useState } from 'react';
import * as agentApi from '../lib/agentSpaceApi';

type DiffFile = {
    path: string;
    patch: string;
};

function parseDiffFiles(diffText: string): DiffFile[] {
    const text = String(diffText || '');
    if (!text.trim()) return [];

    const lines = text.split('\n');
    const files: DiffFile[] = [];
    let currentPath = '';
    let currentLines: string[] = [];

    const pushCurrent = () => {
        if (!currentPath) return;
        files.push({ path: currentPath, patch: currentLines.join('\n').trim() });
        currentPath = '';
        currentLines = [];
    };

    for (let i = 0; i < lines.length; i += 1) {
        const line = lines[i];
        const next = lines[i + 1] || '';
        if (line.startsWith('--- a/') && next.startsWith('+++ b/')) {
            pushCurrent();
            const nextPath = next.slice('+++ b/'.length).trim();
            const oldPath = line.slice('--- a/'.length).trim();
            currentPath = nextPath || oldPath || `file-${files.length + 1}`;
            currentLines = [line, next];
            i += 1;
            continue;
        }
        if (currentPath) currentLines.push(line);
    }

    pushCurrent();
    if (files.length === 0) {
        files.push({ path: 'full.diff', patch: text });
    }
    return files;
}

export default function WorkflowReview() {
    const [advancedMode, setAdvancedMode] = useState(false);
    const [reviews, setReviews] = useState<agentApi.AgentSpaceReview[]>([]);
    const [selectedId, setSelectedId] = useState<string>('');
    const [selected, setSelected] = useState<agentApi.AgentSpaceReview | null>(null);
    const [snapshots, setSnapshots] = useState<Array<Record<string, unknown>>>([]);
    const [rollbackId, setRollbackId] = useState('');
    const [selectedFilePath, setSelectedFilePath] = useState('');
    const [commitMessage, setCommitMessage] = useState('');
    const [committing, setCommitting] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const load = useCallback(async () => {
        try {
            const [reviewRows, snapshotRows] = await Promise.all([
                agentApi.listReviews(300),
                agentApi.listSnapshots(300),
            ]);
            setReviews(reviewRows);
            setSnapshots(snapshotRows);
            if (reviewRows.length > 0 && !selectedId) {
                const preferred = reviewRows.find((row) => row.status === 'pending' || row.status === 'approved');
                setSelectedId(preferred?.id || reviewRows[0].id);
            }
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load review data.');
        }
    }, [selectedId]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (!selectedId) {
            setSelected(null);
            setSelectedFilePath('');
            return;
        }
        agentApi.getReview(selectedId)
            .then((review) => setSelected(review))
            .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load review.'));
    }, [selectedId]);

    const diffFiles = useMemo<DiffFile[]>(() => {
        if (!selected) return [];
        const parsed = parseDiffFiles(selected.diff || '');
        const byPath = new Map(parsed.map((item) => [item.path, item]));
        const payloadChanges = Array.isArray((selected as { changes?: unknown }).changes)
            ? ((selected as { changes?: unknown }).changes as Array<Record<string, unknown>>)
            : [];
        for (const change of payloadChanges) {
            const path = String(change.path || '').replace('\\', '/').trim();
            if (!path) continue;
            if (!byPath.has(path)) {
                byPath.set(path, { path, patch: 'Patch content unavailable for this file in unified diff view.' });
            }
        }
        return Array.from(byPath.values());
    }, [selected]);

    const selectedPatch = useMemo(() => {
        if (!selectedFilePath) return '';
        const row = diffFiles.find((item) => item.path === selectedFilePath);
        return row?.patch || '';
    }, [diffFiles, selectedFilePath]);

    const selectedSummary = useMemo(() => {
        if (!selected) return null;
        if (selected.summary) return selected.summary;
        const changes = Array.isArray(selected.changes) ? selected.changes : [];
        const files = changes.map((change) => ({
            path: String(change.path || ''),
            reason: String(change.reason || 'unknown'),
            added: 0,
            removed: 0,
        }));
        return {
            file_count: files.length || diffFiles.length,
            added_lines: 0,
            removed_lines: 0,
            reason_counts: files.reduce<Record<string, number>>((acc, row) => {
                acc[row.reason] = (acc[row.reason] || 0) + 1;
                return acc;
            }, {}),
            files,
        };
    }, [diffFiles.length, selected]);

    useEffect(() => {
        if (!selected) {
            setSelectedFilePath('');
            setCommitMessage('');
            return;
        }
        const firstPath = diffFiles[0]?.path || '';
        setSelectedFilePath(firstPath);
        setCommitMessage(`feat: apply review ${selected.id.slice(0, 8)}`);
    }, [diffFiles, selected]);

    const selectedSnapshotOptions = useMemo(() => {
        return snapshots.map((item) => String(item.id ?? '')).filter(Boolean);
    }, [snapshots]);

    const nextStepLabel = useMemo(() => {
        if (!selected) return '';
        if (selected.status === 'pending') return 'Approve, reject, or approve+apply this review.';
        if (selected.status === 'approved') return 'Apply it to the workspace or commit it.';
        if (selected.status === 'applied') return selected.snapshot_id
            ? 'Changes are live. Use Undo or Rollback if needed.'
            : 'Changes are live in the workspace.';
        if (selected.status === 'rejected') return 'Rejected reviews stay available for inspection.';
        return '';
    }, [selected]);

    const runAction = useCallback(async (fn: () => Promise<unknown>, successText: string) => {
        setMessage('');
        setError('');
        try {
            await fn();
            setMessage(successText);
            await load();
            if (selectedId) {
                const updated = await agentApi.getReview(selectedId);
                setSelected(updated);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Action failed.');
        }
    }, [load, selectedId]);

    const applySelected = useCallback(async () => {
        if (!selected) return;
        if (selected.status === 'pending') {
            await runAction(async () => {
                await agentApi.approveReview(selected.id);
                await agentApi.applyReview(selected.id);
            }, 'Review approved and applied to workspace.');
            return;
        }
        if (selected.status === 'approved') {
            await runAction(() => agentApi.applyReview(selected.id), 'Review applied to workspace.');
        }
    }, [runAction, selected]);

    const undoSelected = useCallback(async () => {
        if (!selected?.snapshot_id) return;
        await runAction(
            () => agentApi.undoReview(selected.id),
            `Undid review ${selected.id.slice(0, 8)} and restored snapshot ${selected.snapshot_id}.`,
        );
    }, [runAction, selected]);

    const commitSelected = useCallback(async () => {
        if (!selected) return;
        const note = commitMessage.trim();
        if (!note) {
            setError('Commit message is required.');
            return;
        }
        setMessage('');
        setError('');
        setCommitting(true);
        try {
            const result = await agentApi.commitReview(selected.id, { message: note, auto_apply: true });
            const hash = result.commit_id ? ` (${result.commit_id})` : '';
            setMessage(`Committed ${result.files.length} file(s)${hash}.`);
            await load();
            const updated = await agentApi.getReview(selected.id);
            setSelected(updated);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Commit failed.');
        } finally {
            setCommitting(false);
        }
    }, [commitMessage, load, selected]);

    return (
        <div className="h-full overflow-hidden flex flex-col md:flex-row">
            <aside className="md:w-[340px] border-r border-surface-3 bg-surface-1 overflow-auto">
                <div className="p-5 border-b border-surface-3">
                    <div className="flex items-center justify-between gap-2">
                        <h1 className="text-base font-semibold text-text-primary">Workflow Review</h1>
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
                    </div>
                    <p className="text-xs text-text-secondary">
                        Inspect file changes and approve/apply.
                        {advancedMode ? ' Commit + deep summary are visible.' : ' Commit + deep summary are hidden.'}
                    </p>
                </div>
                <div className="p-3 space-y-3">
                    {reviews.length === 0 && <p className="text-xs text-text-secondary p-2">No pending reviews.</p>}
                    {reviews.map((review) => (
                        <button
                            key={review.id}
                            onClick={() => setSelectedId(review.id)}
                            className={`w-full text-left rounded-btn border p-3 ${
                                selectedId === review.id
                                    ? 'bg-surface-2 border-accent/50'
                                    : 'bg-surface-0 border-surface-3 hover:bg-surface-2'
                            }`}
                        >
                            <p className="text-sm text-text-primary truncate">{review.objective}</p>
                            <p className="text-[11px] text-text-secondary mt-1">
                                {review.status} • run {review.run_id.slice(0, 8)}
                            </p>
                        </button>
                    ))}
                </div>
            </aside>

            <section className="flex-1 overflow-auto p-6 md:p-8">
                <div className="mx-auto w-full max-w-6xl space-y-6">
                    {!selected && <p className="text-sm text-text-secondary">Select a review to inspect proposed changes.</p>}
                    {selected && (
                        <>
                            <div className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div>
                                        <h2 className="text-lg font-semibold text-text-primary">{selected.objective}</h2>
                                        <p className="text-xs text-text-secondary mt-1">Review ID: {selected.id}</p>
                                    </div>
                                    <span className={`px-3 py-1 rounded text-xs ${
                                        selected.status === 'approved' ? 'bg-accent-green/15 text-accent-green'
                                            : selected.status === 'rejected' ? 'bg-accent-red/15 text-accent-red'
                                                : selected.status === 'applied' ? 'bg-accent/15 text-accent'
                                                    : 'bg-surface-2 text-text-secondary'
                                    }`}>
                                        {selected.status}
                                    </span>
                                </div>
                                <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
                                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                        <p className="text-[11px] text-text-muted">Files</p>
                                        <p className="mt-1 text-sm text-text-primary">{selectedSummary?.file_count || diffFiles.length || 0}</p>
                                    </div>
                                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                        <p className="text-[11px] text-text-muted">Added</p>
                                        <p className="mt-1 text-sm text-accent-green">+{selectedSummary?.added_lines || 0}</p>
                                    </div>
                                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                        <p className="text-[11px] text-text-muted">Removed</p>
                                        <p className="mt-1 text-sm text-accent-red">-{selectedSummary?.removed_lines || 0}</p>
                                    </div>
                                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                        <p className="text-[11px] text-text-muted">Snapshot</p>
                                        <p className="mt-1 text-sm text-text-primary break-all">
                                            {selected.snapshot_id ? selected.snapshot_id.slice(0, 8) : 'none'}
                                        </p>
                                    </div>
                                </div>
                                {nextStepLabel && (
                                    <div className="mt-4 rounded-btn border border-accent/25 bg-accent/10 p-3 text-xs text-text-primary">
                                        <span className="text-text-secondary">Next step:</span> {nextStepLabel}
                                    </div>
                                )}
                                <div className="mt-4 flex flex-wrap gap-2">
                                    <button
                                        disabled={selected.status !== 'pending'}
                                        onClick={() => runAction(() => agentApi.approveReview(selected.id), 'Review approved.')}
                                        className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green disabled:opacity-40"
                                    >
                                        Approve
                                    </button>
                                    <button
                                        disabled={selected.status !== 'pending'}
                                        onClick={() => runAction(() => agentApi.rejectReview(selected.id, 'Rejected from workflow UI'), 'Review rejected.')}
                                        className="px-3 py-2 rounded-btn border border-accent-red/40 text-accent-red disabled:opacity-40"
                                    >
                                        Reject
                                    </button>
                                    <button
                                        disabled={selected.status !== 'approved' && selected.status !== 'pending'}
                                        onClick={applySelected}
                                        className="px-3 py-2 rounded-btn border border-accent/40 text-accent disabled:opacity-40"
                                    >
                                        {selected.status === 'pending' ? 'Approve + Apply' : 'Apply'}
                                    </button>
                                    <button
                                        disabled={selected.status !== 'applied' || !selected.snapshot_id}
                                        onClick={() => undoSelected().catch(() => {})}
                                        className="px-3 py-2 rounded-btn border border-accent-amber/50 text-accent-amber disabled:opacity-40"
                                    >
                                        Undo
                                    </button>
                                </div>

                                {advancedMode && (
                                    <>
                                        <div className="mt-5">
                                            <p className="text-[11px] uppercase tracking-wide text-text-secondary mb-2">Commit (Editable)</p>
                                            <div className="grid md:grid-cols-[minmax(0,1fr)_120px] gap-2">
                                                <input
                                                    value={commitMessage}
                                                    onChange={(e) => setCommitMessage(e.target.value)}
                                                    className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-sm text-text-primary"
                                                    placeholder="Commit message"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => commitSelected().catch(() => {})}
                                                    disabled={committing || !commitMessage.trim()}
                                                    className="px-3 py-2 rounded-btn border border-accent/40 text-accent disabled:opacity-40"
                                                >
                                                    {committing ? 'Committing...' : 'Commit'}
                                                </button>
                                            </div>
                                        </div>
                                        <p className="mt-2 text-[11px] text-text-muted">
                                            Commit follows GitHub flow: review to apply to commit.
                                        </p>
                                    </>
                                )}
                                {selected.rejection_reason && (
                                    <p className="mt-3 text-xs text-accent-red">Reason: {selected.rejection_reason}</p>
                                )}
                            </div>

                            {selectedSummary && (
                                <div className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                                    <div className="flex items-center justify-between gap-2">
                                        <h3 className="text-sm font-semibold text-text-primary">Change Summary</h3>
                                        {!advancedMode && (
                                            <span className="text-[11px] text-text-muted">Simple mode shows the essentials.</span>
                                        )}
                                    </div>
                                    <p className="text-xs text-text-secondary mt-2">
                                        files changed: {selectedSummary.file_count} • +{selectedSummary.added_lines} / -{selectedSummary.removed_lines}
                                    </p>
                                    <div className="mt-2 flex flex-wrap gap-2">
                                        {Object.entries(selectedSummary.reason_counts || {}).map(([reason, count]) => (
                                            <span key={reason} className="px-2 py-1 rounded-btn border border-surface-4 bg-surface-0 text-[11px] text-text-secondary">
                                                {reason}: {count}
                                            </span>
                                        ))}
                                    </div>
                                    <div className="mt-3 max-h-[180px] overflow-auto space-y-1">
                                        {(selectedSummary.files || []).slice(0, 40).map((row) => (
                                            <div key={`${row.path}-${row.reason}`} className="text-xs text-text-secondary">
                                                {row.path} • {row.reason} • +{row.added} / -{row.removed}
                                            </div>
                                        ))}
                                    </div>
                                    {!advancedMode && (selectedSummary.files || []).length > 6 && (
                                        <p className="mt-3 text-[11px] text-text-muted">
                                            Switch Advanced on for commit controls and deeper diff inspection.
                                        </p>
                                    )}
                                </div>
                            )}

                            <div className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                                <h3 className="text-sm font-semibold text-text-primary">Changed Files</h3>
                                <div className="mt-3 grid md:grid-cols-[260px_minmax(0,1fr)] gap-3">
                                    <div className="max-h-[56vh] overflow-auto space-y-2">
                                        {diffFiles.length === 0 && (
                                            <p className="text-xs text-text-secondary">No file-level diff data available.</p>
                                        )}
                                        {diffFiles.map((file) => (
                                            <button
                                                key={file.path}
                                                type="button"
                                                onClick={() => setSelectedFilePath(file.path)}
                                                className={`w-full text-left rounded-btn border p-2 ${
                                                    selectedFilePath === file.path
                                                        ? 'bg-surface-2 border-accent/50'
                                                        : 'bg-surface-0 border-surface-3 hover:bg-surface-2'
                                                }`}
                                            >
                                                <p className="text-xs text-text-primary break-all">{file.path}</p>
                                            </button>
                                        ))}
                                    </div>
                                    <div className="rounded-btn border border-surface-3 bg-surface-0 p-2">
                                        <p className="text-[11px] text-text-secondary mb-2">{selectedFilePath || 'No file selected'}</p>
                                        <pre className="max-h-[56vh] overflow-auto bg-surface-1 border border-surface-3 p-3 text-xs text-text-primary whitespace-pre-wrap">
                                            {selectedPatch || selected.diff || 'No diff content.'}
                                        </pre>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    <div className="rounded-card border border-surface-3 bg-surface-1 p-5 md:p-6">
                        <h3 className="text-sm font-semibold text-text-primary">Rollback</h3>
                        <p className="text-xs text-text-secondary mt-1">Restore a snapshot created from apply/direct runs.</p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                            <select
                                value={rollbackId}
                                onChange={(e) => setRollbackId(e.target.value)}
                                className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-sm text-text-primary min-w-[260px]"
                            >
                                <option value="">Select snapshot</option>
                                {selectedSnapshotOptions.map((snapshotId) => (
                                    <option key={snapshotId} value={snapshotId}>
                                        {snapshotId}
                                    </option>
                                ))}
                            </select>
                            <button
                                disabled={!rollbackId}
                                onClick={() => runAction(() => agentApi.rollback(rollbackId), `Rolled back snapshot ${rollbackId}.`)}
                                className="px-3 py-2 rounded-btn border border-accent-amber/50 text-accent-amber disabled:opacity-40"
                            >
                                Rollback
                            </button>
                        </div>
                    </div>

                    {message && <p className="text-sm text-accent-green">{message}</p>}
                    {error && <p className="text-sm text-accent-red">{error}</p>}
                </div>
            </section>
        </div>
    );
}
