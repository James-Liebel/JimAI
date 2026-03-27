import { fetchWithTimeout } from './api';

const BASE = '';
const GITHUB_TOKEN_KEY = 'jimai_github_token_v1';

export type GitStatusRow = {
    path: string;
    index_status: string;
    worktree_status: string;
    staged: boolean;
    untracked: boolean;
};

export type GitStatusResponse = {
    branch: string;
    upstream: string;
    ahead: number;
    behind: number;
    origin_url: string;
    token_configured: boolean;
    changes: GitStatusRow[];
};

export type GitBranchRow = {
    name: string;
    current: boolean;
    local: boolean;
    remote: boolean;
};

export type GitCommitRow = {
    hash: string;
    short_hash: string;
    date: string;
    author: string;
    message: string;
};

function authHeaders(): Record<string, string> {
    const token = getStoredGitHubToken();
    return token ? { 'X-GitHub-Token': token } : {};
}

export function getStoredGitHubToken(): string {
    if (typeof window === 'undefined') return '';
    try {
        return window.localStorage.getItem(GITHUB_TOKEN_KEY) || '';
    } catch {
        return '';
    }
}

export function setStoredGitHubToken(token: string): void {
    if (typeof window === 'undefined') return;
    try {
        if (token.trim()) window.localStorage.setItem(GITHUB_TOKEN_KEY, token.trim());
        else window.localStorage.removeItem(GITHUB_TOKEN_KEY);
    } catch {
        // ignore storage failures
    }
}

export async function getGitHubStatus(): Promise<GitStatusResponse> {
    const resp = await fetchWithTimeout(`${BASE}/api/github/status`, { headers: authHeaders() });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github status failed: ${resp.status}`);
    }
    return resp.json();
}

export async function getGitHubLog(): Promise<GitCommitRow[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/github/log`, { headers: authHeaders() });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github log failed: ${resp.status}`);
    }
    const data = await resp.json();
    return Array.isArray(data.commits) ? data.commits : [];
}

export async function getGitHubBranches(): Promise<{ current: string; branches: GitBranchRow[] }> {
    const resp = await fetchWithTimeout(`${BASE}/api/github/branches`, { headers: authHeaders() });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github branches failed: ${resp.status}`);
    }
    const data = await resp.json();
    return {
        current: String(data.current || ''),
        branches: Array.isArray(data.branches) ? data.branches : [],
    };
}

export async function commitGitHubChanges(message: string, files: string[]) {
    const resp = await fetchWithTimeout(`${BASE}/api/github/commit`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...authHeaders(),
        },
        body: JSON.stringify({ message, files }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github commit failed: ${resp.status}`);
    }
    return resp.json();
}

export async function stageGitHubChanges(files: string[], all = false) {
    const resp = await fetchWithTimeout(`${BASE}/api/github/stage`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...authHeaders(),
        },
        body: JSON.stringify({ files, all }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github stage failed: ${resp.status}`);
    }
    return resp.json();
}

export async function unstageGitHubChanges(files: string[], all = false) {
    const resp = await fetchWithTimeout(`${BASE}/api/github/unstage`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...authHeaders(),
        },
        body: JSON.stringify({ files, all }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github unstage failed: ${resp.status}`);
    }
    return resp.json();
}

export async function checkoutGitHubBranch(branch: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/github/checkout`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...authHeaders(),
        },
        body: JSON.stringify({ branch }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github checkout failed: ${resp.status}`);
    }
    return resp.json();
}

export async function pushGitHubChanges() {
    const resp = await fetchWithTimeout(`${BASE}/api/github/push`, {
        method: 'POST',
        headers: authHeaders(),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github push failed: ${resp.status}`);
    }
    return resp.json();
}

export async function pullGitHubChanges() {
    const resp = await fetchWithTimeout(`${BASE}/api/github/pull`, {
        method: 'POST',
        headers: authHeaders(),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `github pull failed: ${resp.status}`);
    }
    return resp.json();
}
