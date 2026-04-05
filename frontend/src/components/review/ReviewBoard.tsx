import { useCallback, useEffect, useMemo, useState } from 'react';
import * as agentApi from '../../lib/agentSpaceApi';
import { inferReviewScope } from '../../lib/reviewScope';
import { cn } from '../../lib/utils';
import { PageHeader } from '../PageHeader';

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

export type ReviewBoardProps = {
    scope: 'workspace' | 'jimai';
    variant: 'page' | 'embedded';
    /** Full-page header (variant page only). */
    pageTitle?: string;
    pageDescription?: string;
    /** Builder: open unified diff in an editor tab. */
    onOpenInEditor?: (review: agentApi.AgentSpaceReview, path: string) => void;
};

export function ReviewBoard({ scope, variant, pageTitle, pageDescription, onOpenInEditor }: ReviewBoardProps) {
    const isEmbedded = variant === 'embedded';
    const [advancedMode, setAdvancedMode] = useState(() => isEmbedded);
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
            const filtered = reviewRows.filter((row) => inferReviewScope(row) === scope);
            setReviews(filtered);
            setSnapshots(snapshotRows);
            setSelectedId((prev) => {
                if (prev && filtered.some((r) => r.id === prev)) return prev;
                if (filtered.length === 0) return '';
                const preferred = filtered.find((row) => row.status === 'pending' || row.status === 'approved');
                return preferred?.id || filtered[0].id;
            });
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load review data.');
        }
    }, [scope]);

    useEffect(() => {
        load().catch(() => {});
    }, [load]);

    useEffect(() => {
        if (!isEmbedded) return undefined;
        const id = window.setInterval(() => {
            load().catch(() => {});
        }, 5000);
        return () => window.clearInterval(id);
    }, [isEmbedded, load]);

    useEffect(() => {
        if (!selectedId) {
            setSelected(null);
            setSelectedFilePath('');
            return;
        }
        agentApi
            .getReview(selectedId)
            .then((review) => setSelected(review))
            .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load review.'));
    }, [selectedId]);

    const diffFiles = useMemo<DiffFile[]>(() => {
        if (!selected) return [];
        const parsed = parseDiffFiles(selected.diff || '');
        const byPath = new Map(parsed.map((item) => [item.path, item]));
        const payloadChanges = Array.isArray(selected.changes) ? selected.changes : [];
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
        if (selected.status === 'applied')
            return selected.snapshot_id
                ? 'Changes are live. Use Undo or Rollback if needed.'
                : 'Changes are live in the workspace.';
        if (selected.status === 'rejected') return 'Rejected reviews stay available for inspection.';
        return '';
    }, [selected]);

    const rejectDetail = scope === 'jimai' ? 'Rejected from JimAI review UI' : 'Rejected from workflow UI';

    const runAction = useCallback(
        async (fn: () => Promise<unknown>, successText: string) => {
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
        },
        [load, selectedId],
    );

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

    const emptyHint =
        scope === 'jimai'
            ? 'No JimAI or self-improvement reviews yet. Runs from SelfCode and self-improvement land here.'
            : 'No workspace reviews in this scope yet. Builder runs and manual tool reviews appear here.';

    const headerTitle = pageTitle ?? (scope === 'jimai' ? 'JimAI review' : 'Workflow review');
    const headerDescription =
        pageDescription ??
        (scope === 'jimai'
            ? 'Inspect changes proposed for the JimAI app itself (self-improvement, models, skills).'
            : 'Inspect file changes and approve or apply.');

    const modeToggle = (
        <button
            type="button"
            onClick={() => setAdvancedMode((prev) => !prev)}
            className={cn(
                'rounded-btn border',
                isEmbedded ? 'px-2 py-1 text-[10px]' : 'px-2.5 py-1.5 text-xs',
                advancedMode ? 'border-accent/40 bg-accent/10 text-accent' : 'border-surface-4 text-text-secondary hover:bg-surface-2',
            )}
        >
            {isEmbedded
                ? advancedMode
                    ? 'Adv'
                    : 'Simple'
                : advancedMode
                  ? 'Advanced: ON'
                  : 'Simple: ON'}
        </button>
    );

    return (
        <div
            className={cn(
                'min-h-0 overflow-hidden flex',
                isEmbedded ? 'h-full flex-col bg-[#1A1A1E]' : 'h-full flex-col md:flex-row',
            )}
        >
            <aside
                className={cn(
                    'border-surface-4 bg-surface-1 overflow-auto flex flex-col min-h-0',
                    isEmbedded ? 'max-h-[40%] shrink-0 border-b border-[#2A2A30]' : 'md:w-[340px] md:max-h-none md:border-r',
                )}
            >
                {isEmbedded ? (
                    <div className="flex items-center justify-between gap-2 border-b border-[#2A2A30] px-2 py-2 shrink-0">
                        <div className="min-w-0">
                            <p className="text-[11px] font-medium text-text-primary truncate">Reviews</p>
                            <p className="text-[10px] text-text-muted truncate">Approve, apply, commit</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                            <button
                                type="button"
                                onClick={() => load().catch(() => {})}
                                className="rounded-btn border border-[#2A2A30] px-2 py-1 text-[10px] text-text-secondary hover:bg-[#25252c]"
                            >
                                Refresh
                            </button>
                            {modeToggle}
                        </div>
                    </div>
                ) : (
                    <div className="p-5 border-b border-surface-4">
                        <PageHeader
                            variant="embedded"
                            className="!pb-0"
                            title={headerTitle}
                            description={`${headerDescription} ${advancedMode ? 'Commit + full summary visible.' : 'Commit + deep summary hidden.'}`}
                            actions={modeToggle}
                        />
                    </div>
                )}
                <div className={cn('space-y-2 overflow-auto flex-1 min-h-0', isEmbedded ? 'p-2' : 'p-3 space-y-3')}>
                    {reviews.length === 0 && <p className="text-xs text-text-secondary p-2">{emptyHint}</p>}
                    {reviews.map((review) => (
                        <button
                            key={review.id}
                            type="button"
                            onClick={() => setSelectedId(review.id)}
                            className={cn(
                                'w-full text-left rounded-btn border',
                                isEmbedded ? 'p-2' : 'p-3',
                                selectedId === review.id
                                    ? 'bg-surface-2 border-accent/50'
                                    : 'bg-surface-0 border-surface-4 hover:bg-surface-2',
                            )}
                        >
                            <p className={cn('text-text-primary truncate', isEmbedded ? 'text-[11px]' : 'text-sm')}>
                                {review.objective}
                            </p>
                            <p className="text-[10px] text-text-secondary mt-0.5">
                                {review.status} · run {review.run_id.slice(0, 8)}
                            </p>
                        </button>
                    ))}
                </div>
            </aside>

            <section className={cn('flex-1 overflow-auto min-h-0', isEmbedded ? 'p-2' : 'p-6 md:p-10')}>
                <div
                    className={cn(
                        'mx-auto w-full space-y-4',
                        !isEmbedded && 'max-w-[min(112rem,calc(100%-2rem))] space-y-6',
                    )}
                >
                    {!selected && <p className="text-sm text-text-secondary">Select a review to inspect proposed changes.</p>}
                    {selected && (
                        <>
                            <div
                                className={cn(
                                    'rounded-card border border-surface-4 bg-surface-1',
                                    isEmbedded ? 'p-3' : 'p-5 md:p-6',
                                )}
                            >
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <h2
                                            className={cn(
                                                'font-semibold text-text-primary',
                                                isEmbedded ? 'text-xs line-clamp-3' : 'text-base',
                                            )}
                                        >
                                            {selected.objective}
                                        </h2>
                                        <p className="text-[10px] text-text-secondary mt-1 font-mono truncate">ID {selected.id.slice(0, 8)}…</p>
                                    </div>
                                    <span
                                        className={cn(
                                            'px-2 py-0.5 rounded text-[10px] shrink-0',
                                            selected.status === 'approved'
                                                ? 'bg-accent-green/15 text-accent-green'
                                                : selected.status === 'rejected'
                                                  ? 'bg-accent-red/15 text-accent-red'
                                                  : selected.status === 'applied'
                                                    ? 'bg-accent/15 text-accent'
                                                    : 'bg-surface-2 text-text-secondary',
                                        )}
                                    >
                                        {selected.status}
                                    </span>
                                </div>
                                <div
                                    className={cn(
                                        'mt-3 grid gap-1.5',
                                        isEmbedded ? 'grid-cols-2' : 'grid-cols-2 md:grid-cols-4 gap-2',
                                    )}
                                >
                                    <div className="rounded-btn border border-surface-4 bg-surface-0 p-2">
                                        <p className="text-[10px] text-text-muted">Files</p>
                                        <p className="mt-0.5 text-xs text-text-primary">{selectedSummary?.file_count || diffFiles.length || 0}</p>
                                    </div>
                                    <div className="rounded-btn border border-surface-4 bg-surface-0 p-2">
                                        <p className="text-[10px] text-text-muted">Added</p>
                                        <p className="mt-0.5 text-xs text-accent-green">+{selectedSummary?.added_lines || 0}</p>
                                    </div>
                                    <div className="rounded-btn border border-surface-4 bg-surface-0 p-2">
                                        <p className="text-[10px] text-text-muted">Removed</p>
                                        <p className="mt-0.5 text-xs text-accent-red">-{selectedSummary?.removed_lines || 0}</p>
                                    </div>
                                    <div className="rounded-btn border border-surface-4 bg-surface-0 p-2">
                                        <p className="text-[10px] text-text-muted">Snapshot</p>
                                        <p className="mt-0.5 text-xs text-text-primary break-all">
                                            {selected.snapshot_id ? selected.snapshot_id.slice(0, 8) : '—'}
                                        </p>
                                    </div>
                                </div>
                                {nextStepLabel && (
                                    <div className="mt-3 rounded-btn border border-accent/25 bg-accent/10 p-2 text-[10px] text-text-primary">
                                        <span className="text-text-secondary">Next:</span> {nextStepLabel}
                                    </div>
                                )}
                                <div className="mt-3 flex flex-wrap gap-1.5">
                                    <button
                                        type="button"
                                        disabled={selected.status !== 'pending'}
                                        onClick={() => runAction(() => agentApi.approveReview(selected.id), 'Review approved.')}
                                        className="px-2 py-1.5 rounded-btn border border-accent-green/40 text-[10px] text-accent-green disabled:opacity-40"
                                    >
                                        Approve
                                    </button>
                                    <button
                                        type="button"
                                        disabled={selected.status !== 'pending'}
                                        onClick={() => runAction(() => agentApi.rejectReview(selected.id, rejectDetail), 'Review rejected.')}
                                        className="px-2 py-1.5 rounded-btn border border-accent-red/40 text-[10px] text-accent-red disabled:opacity-40"
                                    >
                                        Reject
                                    </button>
                                    <button
                                        type="button"
                                        disabled={selected.status !== 'approved' && selected.status !== 'pending'}
                                        onClick={() => applySelected().catch(() => {})}
                                        className="px-2 py-1.5 rounded-btn border border-accent/40 text-[10px] text-accent disabled:opacity-40"
                                    >
                                        {selected.status === 'pending' ? 'Approve+Apply' : 'Apply'}
                                    </button>
                                    <button
                                        type="button"
                                        disabled={selected.status !== 'applied' || !selected.snapshot_id}
                                        onClick={() => undoSelected().catch(() => {})}
                                        className="px-2 py-1.5 rounded-btn border border-accent-amber/50 text-[10px] text-accent-amber disabled:opacity-40"
                                    >
                                        Undo
                                    </button>
                                </div>

                                {advancedMode && (
                                    <>
                                        <div className="mt-4">
                                            <p className="text-[10px] uppercase tracking-wide text-text-secondary mb-1.5">Commit</p>
                                            <div className="grid grid-cols-1 gap-1.5 md:grid-cols-[minmax(0,1fr)_100px]">
                                                <input
                                                    value={commitMessage}
                                                    onChange={(e) => setCommitMessage(e.target.value)}
                                                    className="bg-surface-0 border border-surface-4 rounded-btn px-2 py-1.5 text-xs text-text-primary"
                                                    placeholder="Commit message"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => commitSelected().catch(() => {})}
                                                    disabled={committing || !commitMessage.trim()}
                                                    className="px-2 py-1.5 rounded-btn border border-accent/40 text-xs text-accent disabled:opacity-40"
                                                >
                                                    {committing ? '…' : 'Commit'}
                                                </button>
                                            </div>
                                        </div>
                                        <p className="mt-1.5 text-[10px] text-text-muted">Review → apply → commit (Git).</p>
                                    </>
                                )}
                                {selected.rejection_reason && (
                                    <p className="mt-2 text-[10px] text-accent-red">Reason: {selected.rejection_reason}</p>
                                )}
                            </div>

                            {selectedSummary && advancedMode && (
                                <div
                                    className={cn(
                                        'rounded-card border border-surface-4 bg-surface-1',
                                        isEmbedded ? 'p-3' : 'p-5 md:p-6',
                                    )}
                                >
                                    <h3 className="text-xs font-semibold text-text-primary">Change summary</h3>
                                    <p className="text-[10px] text-text-secondary mt-1">
                                        {selectedSummary.file_count} files · +{selectedSummary.added_lines} / -{selectedSummary.removed_lines}
                                    </p>
                                    <div className="mt-2 max-h-[100px] overflow-auto space-y-0.5">
                                        {(selectedSummary.files || []).slice(0, 20).map((row) => (
                                            <div key={`${row.path}-${row.reason}`} className="text-[10px] text-text-secondary truncate">
                                                {row.path}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            <div
                                className={cn(
                                    'rounded-card border border-surface-4 bg-surface-1',
                                    isEmbedded ? 'p-3' : 'p-5 md:p-6',
                                )}
                            >
                                <h3 className="text-xs font-semibold text-text-primary">Changed files</h3>
                                <div
                                    className={cn(
                                        'mt-2 gap-2',
                                        isEmbedded ? 'flex flex-col' : 'grid md:grid-cols-[260px_minmax(0,1fr)]',
                                    )}
                                >
                                    <div className={cn('overflow-auto space-y-1', isEmbedded ? 'max-h-[120px]' : 'max-h-[56vh]')}>
                                        {diffFiles.length === 0 && (
                                            <p className="text-[10px] text-text-secondary">No file-level diff data.</p>
                                        )}
                                        {diffFiles.map((file) => (
                                            <div key={file.path} className="flex gap-1">
                                                <button
                                                    type="button"
                                                    onClick={() => setSelectedFilePath(file.path)}
                                                    className={cn(
                                                        'min-w-0 flex-1 text-left rounded-btn border p-1.5',
                                                        selectedFilePath === file.path
                                                            ? 'bg-surface-2 border-accent/50'
                                                            : 'bg-surface-0 border-surface-4 hover:bg-surface-2',
                                                    )}
                                                >
                                                    <p className="text-[10px] text-text-primary break-all">{file.path}</p>
                                                </button>
                                                {onOpenInEditor && selected && (
                                                    <button
                                                        type="button"
                                                        onClick={() => onOpenInEditor(selected, file.path)}
                                                        className="shrink-0 rounded-btn border border-[#2A2A30] px-2 py-1 text-[10px] text-text-muted hover:text-text-primary"
                                                    >
                                                        Tab
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                    <div className="rounded-btn border border-surface-4 bg-surface-0 p-2 min-h-0">
                                        <p className="text-[10px] text-text-secondary mb-1">{selectedFilePath || 'No file'}</p>
                                        <pre
                                            className={cn(
                                                'overflow-auto bg-surface-1 border border-surface-4 p-2 text-[10px] text-text-primary whitespace-pre-wrap',
                                                isEmbedded ? 'max-h-[28vh]' : 'max-h-[56vh]',
                                            )}
                                        >
                                            {selectedPatch || selected.diff || 'No diff.'}
                                        </pre>
                                    </div>
                                </div>
                            </div>
                        </>
                    )}

                    {!isEmbedded && (
                        <div className="rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6">
                            <h3 className="text-sm font-semibold text-text-primary">Rollback</h3>
                            <p className="text-xs text-text-secondary mt-1">Restore a snapshot from apply/direct runs.</p>
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
                                    type="button"
                                    disabled={!rollbackId}
                                    onClick={() => runAction(() => agentApi.rollback(rollbackId), `Rolled back snapshot ${rollbackId}.`)}
                                    className="px-3 py-2 rounded-btn border border-accent-amber/50 text-accent-amber disabled:opacity-40"
                                >
                                    Rollback
                                </button>
                            </div>
                        </div>
                    )}

                    {message && <p className="text-xs text-accent-green">{message}</p>}
                    {error && <p className="text-xs text-accent-red">{error}</p>}
                </div>
            </section>
        </div>
    );
}
