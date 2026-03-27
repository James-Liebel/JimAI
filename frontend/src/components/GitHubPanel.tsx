import { useEffect, useMemo, useState } from 'react';
import {
    checkoutGitHubBranch,
    commitGitHubChanges,
    getGitHubBranches,
    getGitHubLog,
    getGitHubStatus,
    getStoredGitHubToken,
    pullGitHubChanges,
    pushGitHubChanges,
    setStoredGitHubToken,
    stageGitHubChanges,
    unstageGitHubChanges,
    type GitBranchRow,
    type GitCommitRow,
    type GitStatusResponse,
} from '../lib/githubApi';

export default function GitHubPanel({
    open,
    onClose,
    onRepositoryChanged,
}: {
    open: boolean;
    onClose: () => void;
    onRepositoryChanged?: () => void | Promise<void>;
}) {
    const [status, setStatus] = useState<GitStatusResponse | null>(null);
    const [branches, setBranches] = useState<GitBranchRow[]>([]);
    const [commits, setCommits] = useState<GitCommitRow[]>([]);
    const [token, setToken] = useState('');
    const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
    const [targetBranch, setTargetBranch] = useState('');
    const [commitMessage, setCommitMessage] = useState('');
    const [loading, setLoading] = useState(false);
    const [working, setWorking] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const load = async () => {
        setLoading(true);
        setError('');
        try {
            const [nextStatus, nextLog, nextBranches] = await Promise.all([
                getGitHubStatus(),
                getGitHubLog(),
                getGitHubBranches(),
            ]);
            setStatus(nextStatus);
            setCommits(nextLog);
            setBranches(nextBranches.branches);
            setTargetBranch((prev) => prev && nextBranches.branches.some((row) => row.name === prev) ? prev : nextBranches.current || nextStatus.branch || '');
            setSelectedFiles((prev) => prev.filter((path) => nextStatus.changes.some((row) => row.path === path)));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load GitHub status.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!open) return;
        setToken(getStoredGitHubToken());
        load().catch(() => undefined);
    }, [open]);

    const allChangedPaths = useMemo(
        () => (status?.changes || []).map((row) => row.path),
        [status],
    );
    const stagedCount = useMemo(
        () => (status?.changes || []).filter((row) => row.staged).length,
        [status],
    );
    const selectedRows = useMemo(
        () => (status?.changes || []).filter((row) => selectedFiles.includes(row.path)),
        [selectedFiles, status],
    );

    const saveToken = () => {
        setStoredGitHubToken(token);
        setMessage(token.trim() ? 'GitHub token saved locally in this browser.' : 'GitHub token cleared.');
        setError('');
    };

    const toggleFile = (path: string) => {
        setSelectedFiles((prev) => (prev.includes(path) ? prev.filter((row) => row !== path) : [...prev, path]));
    };

    const runStage = async (all = false) => {
        if (!all && selectedFiles.length === 0) {
            setError('Select at least one file to stage.');
            return;
        }
        setWorking(true);
        setMessage('');
        setError('');
        try {
            await stageGitHubChanges(all ? [] : selectedFiles, all);
            setMessage(all ? 'Staged all changes.' : `Staged ${selectedFiles.length} file(s).`);
            await load();
            await onRepositoryChanged?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Stage failed.');
        } finally {
            setWorking(false);
        }
    };

    const runUnstage = async (all = false) => {
        if (!all && selectedFiles.length === 0) {
            setError('Select at least one file to unstage.');
            return;
        }
        setWorking(true);
        setMessage('');
        setError('');
        try {
            await unstageGitHubChanges(all ? [] : selectedFiles, all);
            setMessage(all ? 'Unstaged all files.' : `Unstaged ${selectedFiles.length} file(s).`);
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unstage failed.');
        } finally {
            setWorking(false);
        }
    };

    const runCommit = async () => {
        if (!commitMessage.trim()) {
            setError('Enter a commit message first.');
            return;
        }
        setWorking(true);
        setMessage('');
        setError('');
        try {
            await commitGitHubChanges(commitMessage.trim(), []);
            setCommitMessage('');
            setMessage(`Committed ${stagedCount} staged file(s).`);
            await load();
            await onRepositoryChanged?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Commit failed.');
        } finally {
            setWorking(false);
        }
    };

    const runCheckout = async () => {
        if (!targetBranch.trim()) {
            setError('Choose a branch first.');
            return;
        }
        setWorking(true);
        setMessage('');
        setError('');
        try {
            const data = await checkoutGitHubBranch(targetBranch.trim());
            setMessage(String(data.output || `Switched to ${targetBranch.trim()}.`));
            await load();
            await onRepositoryChanged?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Checkout failed.');
        } finally {
            setWorking(false);
        }
    };

    const runPush = async () => {
        setWorking(true);
        setMessage('');
        setError('');
        try {
            await pushGitHubChanges();
            setMessage('Pushed to origin.');
            await load();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Push failed.');
        } finally {
            setWorking(false);
        }
    };

    const runPull = async () => {
        setWorking(true);
        setMessage('');
        setError('');
        try {
            await pullGitHubChanges();
            setMessage('Pulled latest from origin.');
            await load();
            await onRepositoryChanged?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Pull failed.');
        } finally {
            setWorking(false);
        }
    };

    if (!open) return null;

    return (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
            <div className="flex h-[80vh] w-full max-w-5xl flex-col overflow-hidden rounded-card border border-surface-3 bg-surface-1 shadow-2xl">
                <div className="flex items-center justify-between gap-3 border-b border-surface-3 px-4 py-3">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-text-secondary">GitHub</p>
                        <h2 className="mt-1 text-lg font-semibold text-text-primary">Branch, stage, commit, push, and pull</h2>
                    </div>
                    <div className="flex items-center gap-2">
                        <button type="button" onClick={() => load().catch(() => undefined)} className="rounded-btn border border-surface-4 px-3 py-1.5 text-xs text-text-primary hover:bg-surface-2">
                            {loading ? 'Refreshing…' : 'Refresh'}
                        </button>
                        <button type="button" onClick={onClose} className="rounded-btn border border-surface-4 px-3 py-1.5 text-xs text-text-primary hover:bg-surface-2">
                            Close
                        </button>
                    </div>
                </div>

                <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 lg:grid-cols-[minmax(0,1fr)_360px]">
                    <div className="min-h-0 overflow-auto p-4 space-y-4">
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Connection</p>
                            <input
                                value={token}
                                onChange={(e) => setToken(e.target.value)}
                                type="password"
                                className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-3 py-2 text-sm text-black outline-none"
                                placeholder="GitHub token (stored only in localStorage)"
                            />
                            <div className="mt-2 flex gap-2">
                                <button type="button" onClick={saveToken} className="rounded-btn border border-accent/40 px-3 py-1.5 text-xs text-accent">
                                    Save Token
                                </button>
                                <button type="button" onClick={() => { setToken(''); setStoredGitHubToken(''); }} className="rounded-btn border border-surface-4 px-3 py-1.5 text-xs text-text-primary hover:bg-surface-2">
                                    Clear
                                </button>
                            </div>
                        </div>

                        <div className="grid gap-3 md:grid-cols-4">
                            <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] text-text-muted">Branch</p>
                                <p className="mt-1 text-sm text-text-primary">{status?.branch || '...'}</p>
                            </div>
                            <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] text-text-muted">Upstream</p>
                                <p className="mt-1 truncate text-sm text-text-primary">{status?.upstream || 'origin'}</p>
                            </div>
                            <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] text-text-muted">Ahead / Behind</p>
                                <p className="mt-1 text-sm text-text-primary">{status ? `${status.ahead}/${status.behind}` : '0/0'}</p>
                            </div>
                            <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                                <p className="text-[11px] text-text-muted">Changed / Staged</p>
                                <p className="mt-1 text-sm text-text-primary">{status?.changes.length || 0} / {stagedCount}</p>
                            </div>
                        </div>

                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <div className="flex items-center justify-between gap-2">
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary">Branches</p>
                                <span className="text-[11px] text-text-secondary">{branches.length} available</span>
                            </div>
                            <div className="mt-3 flex gap-2">
                                <select
                                    value={targetBranch}
                                    onChange={(e) => setTargetBranch(e.target.value)}
                                    className="flex-1 rounded-btn border border-surface-4 bg-white px-3 py-2 text-sm text-black outline-none"
                                >
                                    <option value="">Select branch</option>
                                    {branches.map((row) => (
                                        <option key={row.name} value={row.name}>
                                            {row.name}{row.current ? ' (current)' : ''}{row.remote && !row.local ? ' (remote)' : ''}
                                        </option>
                                    ))}
                                </select>
                                <button
                                    type="button"
                                    onClick={() => runCheckout().catch(() => undefined)}
                                    disabled={working || !targetBranch || targetBranch === status?.branch}
                                    className="rounded-btn border border-accent/40 px-3 py-2 text-xs text-accent disabled:opacity-50"
                                >
                                    Checkout
                                </button>
                            </div>
                        </div>

                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <div className="flex items-center justify-between gap-2">
                                <p className="text-[11px] uppercase tracking-wide text-text-secondary">Working tree</p>
                                <div className="flex gap-2">
                                    <button type="button" onClick={() => setSelectedFiles(allChangedPaths)} className="rounded-btn border border-surface-4 px-2 py-1 text-[11px] text-text-primary hover:bg-surface-2">
                                        Select all
                                    </button>
                                    <button type="button" onClick={() => setSelectedFiles([])} className="rounded-btn border border-surface-4 px-2 py-1 text-[11px] text-text-primary hover:bg-surface-2">
                                        Clear
                                    </button>
                                </div>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                                <button type="button" onClick={() => runStage(false).catch(() => undefined)} disabled={working || selectedFiles.length === 0} className="rounded-btn border border-accent/40 px-2 py-1 text-[11px] text-accent disabled:opacity-50">
                                    Stage selected
                                </button>
                                <button type="button" onClick={() => runStage(true).catch(() => undefined)} disabled={working || (status?.changes.length || 0) === 0} className="rounded-btn border border-surface-4 px-2 py-1 text-[11px] text-text-primary hover:bg-surface-2 disabled:opacity-50">
                                    Stage all
                                </button>
                                <button type="button" onClick={() => runUnstage(false).catch(() => undefined)} disabled={working || selectedFiles.length === 0} className="rounded-btn border border-surface-4 px-2 py-1 text-[11px] text-text-primary hover:bg-surface-2 disabled:opacity-50">
                                    Unstage selected
                                </button>
                                <button type="button" onClick={() => runUnstage(true).catch(() => undefined)} disabled={working || stagedCount === 0} className="rounded-btn border border-surface-4 px-2 py-1 text-[11px] text-text-primary hover:bg-surface-2 disabled:opacity-50">
                                    Unstage all
                                </button>
                            </div>
                            <p className="mt-2 text-[11px] text-text-secondary">
                                Selected: {selectedFiles.length} file(s) · staged among selection: {selectedRows.filter((row) => row.staged).length}
                            </p>
                            <div className="mt-3 space-y-2">
                                {(status?.changes || []).length === 0 && <p className="text-xs text-text-secondary">Working tree is clean.</p>}
                                {(status?.changes || []).map((row) => (
                                    <label key={row.path} className="flex items-center gap-3 rounded-btn border border-surface-3 bg-surface-1 px-3 py-2 text-xs">
                                        <input checked={selectedFiles.includes(row.path)} onChange={() => toggleFile(row.path)} type="checkbox" />
                                        <span className="min-w-[36px] rounded-full border border-surface-4 px-2 py-0.5 text-[10px] text-text-secondary">
                                            {row.index_status}{row.worktree_status}
                                        </span>
                                        <span className="flex-1 text-text-primary">{row.path}</span>
                                        <span className="text-text-muted">{row.untracked ? 'untracked' : row.staged ? 'staged' : 'unstaged'}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="min-h-0 overflow-auto border-t border-l border-surface-3 bg-surface-1 p-4 space-y-4 lg:border-t-0">
                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Commit staged changes</p>
                            <textarea
                                rows={3}
                                value={commitMessage}
                                onChange={(e) => setCommitMessage(e.target.value)}
                                className="mt-2 w-full rounded-btn border border-surface-4 bg-white px-3 py-2 text-sm text-black outline-none"
                                placeholder="Write a commit message"
                            />
                            <p className="mt-2 text-[11px] text-text-secondary">
                                Currently staged: {stagedCount} file(s)
                            </p>
                            <button type="button" onClick={() => runCommit().catch(() => undefined)} disabled={working || stagedCount === 0} className="mt-3 w-full rounded-btn border border-accent/40 px-3 py-2 text-xs text-accent disabled:opacity-50">
                                {working ? 'Working…' : 'Commit Staged Changes'}
                            </button>
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                            <button type="button" onClick={() => runPull().catch(() => undefined)} disabled={working} className="rounded-btn border border-surface-4 px-3 py-2 text-xs text-text-primary hover:bg-surface-2 disabled:opacity-50">
                                Pull Latest
                            </button>
                            <button type="button" onClick={() => runPush().catch(() => undefined)} disabled={working} className="rounded-btn border border-accent-green/40 px-3 py-2 text-xs text-accent-green disabled:opacity-50">
                                Push to Origin
                            </button>
                        </div>

                        <div className="rounded-card border border-surface-3 bg-surface-0 p-3">
                            <p className="text-[11px] uppercase tracking-wide text-text-secondary">Recent commits</p>
                            <div className="mt-3 space-y-2">
                                {commits.map((row) => (
                                    <div key={row.hash} className="rounded-btn border border-surface-3 bg-surface-1 p-2">
                                        <p className="text-xs text-text-primary">{row.message}</p>
                                        <p className="mt-1 text-[11px] text-text-secondary">
                                            {row.short_hash} · {row.author}
                                        </p>
                                        <p className="mt-1 text-[10px] text-text-muted">{row.date}</p>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {message && <p className="text-sm text-accent-green">{message}</p>}
                        {error && <p className="text-sm text-accent-red">{error}</p>}
                    </div>
                </div>
            </div>
        </div>
    );
}
