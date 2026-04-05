import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Github, Loader2, X } from 'lucide-react';
import {
    getStoredGitHubToken,
    listGitHubRemoteRepos,
    setStoredGitHubToken,
    type GitHubRemoteRepo,
} from '../../lib/githubApi';
import { cn } from '../../lib/utils';

type Props = {
    open: boolean;
    onClose: () => void;
    /** Clone HTTPS URL into folder `folderName` (sanitized by caller if needed). */
    onClone: (cloneUrl: string, folderName: string) => Promise<void>;
};

export function BuilderGitHubCloneModal({ open, onClose, onClone }: Props) {
    const [tokenInput, setTokenInput] = useState('');
    const [repos, setRepos] = useState<GitHubRemoteRepo[]>([]);
    const [loading, setLoading] = useState(false);
    const [cloningId, setCloningId] = useState<number | null>(null);
    const [error, setError] = useState('');
    const [filter, setFilter] = useState('');
    const [storedToken, setStoredToken] = useState(false);

    const loadRepos = useCallback(async () => {
        if (!getStoredGitHubToken().trim()) {
            setRepos([]);
            return;
        }
        setLoading(true);
        setError('');
        try {
            setRepos(await listGitHubRemoteRepos(250));
        } catch (e) {
            setRepos([]);
            setError(e instanceof Error ? e.message : 'Could not load repositories.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!open) return;
        setTokenInput(getStoredGitHubToken());
        setStoredToken(Boolean(getStoredGitHubToken().trim()));
        setFilter('');
        setError('');
        void loadRepos();
    }, [open, loadRepos]);

    const filtered = useMemo(() => {
        const q = filter.trim().toLowerCase();
        if (!q) return repos;
        return repos.filter(
            (r) =>
                r.full_name.toLowerCase().includes(q) ||
                (r.description || '').toLowerCase().includes(q) ||
                r.name.toLowerCase().includes(q),
        );
    }, [filter, repos]);

    const saveToken = () => {
        setStoredGitHubToken(tokenInput);
        setStoredToken(Boolean(tokenInput.trim()));
        setError('');
        void loadRepos();
    };

    const pick = async (repo: GitHubRemoteRepo) => {
        if (!repo.clone_url) return;
        setCloningId(repo.id);
        setError('');
        try {
            await onClone(repo.clone_url, repo.name);
            onClose();
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Clone failed.');
        } finally {
            setCloningId(null);
        }
    };

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 px-3 py-10 sm:py-14" role="dialog" aria-modal="true" aria-labelledby="gh-clone-title">
            <button type="button" className="absolute inset-0 cursor-default" aria-label="Close" onClick={onClose} />
            <div className="relative z-10 flex max-h-[min(85vh,720px)] w-full max-w-lg flex-col overflow-hidden rounded-lg border border-[#2A2A30] bg-[#1A1A1E] shadow-xl">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[#2A2A30] px-4 py-3">
                    <div className="flex min-w-0 items-center gap-2">
                        <Github className="h-5 w-5 shrink-0 text-text-secondary" aria-hidden />
                        <h2 id="gh-clone-title" className="truncate text-sm font-semibold text-text-primary">
                            Clone from GitHub
                        </h2>
                    </div>
                    <button type="button" onClick={onClose} className="rounded p-1 text-text-muted hover:bg-white/[0.06] hover:text-text-primary" aria-label="Close">
                        <X className="h-4 w-4" />
                    </button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
                    <p className="text-[12px] leading-relaxed text-text-muted">
                        Uses the same personal access token as the{' '}
                        <Link to="/settings" className="text-[#93C5FD] hover:underline" onClick={onClose}>
                            Settings
                        </Link>{' '}
                        / Git panel. Classic PAT needs <code className="font-mono text-[11px] text-text-secondary">repo</code> scope; fine-grained needs read access to
                        repositories.
                    </p>
                    <div className="mt-3 space-y-2">
                        <label className="sr-only" htmlFor="gh-clone-token">
                            GitHub token
                        </label>
                        <input
                            id="gh-clone-token"
                            type="password"
                            autoComplete="off"
                            value={tokenInput}
                            onChange={(e) => setTokenInput(e.target.value)}
                            placeholder="ghp_… or github_pat_…"
                            className="w-full rounded-md border border-[#2A2A30] bg-[#0F0F12] px-3 py-2 font-mono text-[12px] text-text-primary outline-none placeholder:text-[#55556A] focus:border-[#3B82F6]"
                        />
                        <div className="flex flex-wrap gap-2">
                            <button
                                type="button"
                                onClick={() => saveToken()}
                                className="rounded-md border border-[#2A2A30] bg-[#222228] px-3 py-1.5 text-[12px] font-medium text-text-secondary transition-colors hover:border-[#3B82F6]/40 hover:text-text-primary"
                            >
                                Save token
                            </button>
                            <button
                                type="button"
                                onClick={() => void loadRepos()}
                                disabled={loading || !storedToken}
                                className="rounded-md border border-[#3B82F6]/35 px-3 py-1.5 text-[12px] font-medium text-[#93C5FD] transition-colors hover:bg-[#3B82F6]/10 disabled:opacity-40"
                            >
                                Refresh list
                            </button>
                        </div>
                    </div>
                    {error && <p className="mt-3 text-[12px] text-accent-red">{error}</p>}
                    <div className="mt-4">
                        <label className="sr-only" htmlFor="gh-clone-filter">
                            Filter repositories
                        </label>
                        <input
                            id="gh-clone-filter"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            placeholder="Filter by name…"
                            disabled={!repos.length && !loading}
                            className="w-full rounded-md border border-[#2A2A30] bg-[#0F0F12] px-3 py-2 text-[13px] text-text-primary outline-none placeholder:text-[#55556A] focus:border-[#3B82F6]"
                        />
                    </div>
                    <div className="mt-2 min-h-[200px]">
                        {loading ? (
                            <div className="flex items-center justify-center gap-2 py-12 text-[12px] text-text-muted">
                                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                                Loading your repositories…
                            </div>
                        ) : !storedToken ? (
                            <p className="py-8 text-center text-[12px] text-text-muted">Save a GitHub token above to load repositories.</p>
                        ) : filtered.length === 0 ? (
                            <p className="py-8 text-center text-[12px] text-text-muted">No matching repositories.</p>
                        ) : (
                            <ul className="space-y-1 pr-1">
                                {filtered.map((repo) => (
                                    <li key={repo.id}>
                                        <button
                                            type="button"
                                            disabled={cloningId !== null}
                                            onClick={() => pick(repo).catch(() => undefined)}
                                            className={cn(
                                                'flex w-full flex-col gap-0.5 rounded-md border border-transparent px-2.5 py-2 text-left transition-colors',
                                                'hover:border-[#3B82F6]/30 hover:bg-[#3B82F6]/8',
                                                cloningId === repo.id && 'border-[#3B82F6]/40 bg-[#3B82F6]/10',
                                            )}
                                        >
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="truncate font-mono text-[12px] font-medium text-text-primary">{repo.full_name}</span>
                                                {repo.private && (
                                                    <span className="shrink-0 rounded border border-[#2A2A30] px-1 py-0.5 text-[9px] uppercase tracking-wide text-text-muted">Private</span>
                                                )}
                                            </div>
                                            {repo.description ? (
                                                <span className="line-clamp-2 text-[11px] text-text-muted">{repo.description}</span>
                                            ) : null}
                                            {cloningId === repo.id ? (
                                                <span className="text-[10px] text-[#93C5FD]">Cloning…</span>
                                            ) : (
                                                <span className="font-mono text-[10px] text-text-muted">→ {repo.name}</span>
                                            )}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
