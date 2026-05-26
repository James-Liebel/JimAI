/**
 * Pure helpers, type definitions, and storage keys for the Builder page.
 *
 * Extracted verbatim from `pages/Builder.tsx` to slim the page component down to
 * its stateful logic and layout. No behavioural change — these are imported back
 * into Builder and its subcomponents.
 */
import * as agentApi from '../../lib/agentSpaceApi';

export const BUILDER_MODEL_CHOICE_KEY = 'jimai-builder-model-choice';
export const BUILDER_WORKSPACE_UNLOCKED_KEY = 'jimai-builder-workspace-unlocked';

export type AgentChatLine = { id: string; role: 'user' | 'assistant' | 'system'; content: string; at: number };

export function readSessionBuilderUnlocked(): boolean {
    try {
        return sessionStorage.getItem(BUILDER_WORKSPACE_UNLOCKED_KEY) === '1';
    } catch {
        return false;
    }
}

export type NodeStatus = 'idle' | 'pending' | 'running' | 'completed' | 'failed';
export type PendingCreate = { parentPath: string; kind: 'file' | 'folder'; value: string };
export type TerminalRow = { id: string; command: string; cwd: string; exitCode: number; stdout: string; stderr: string; timestamp: number };
export type FlowNode = { id: string; role: string; workerLevel: number; dependsOn: string[]; description?: string; status?: NodeStatus };
export type FileTab = { id: string; type: 'file'; title: string; path: string; content: string; dirty: boolean; language: string };
export type DiffTab = { id: string; type: 'diff'; title: string; path: string; reviewId: string; reviewStatus: string; original: string; modified: string };
export type Tab = FileTab | DiffTab;
export type ActivityRow = { id: string; timestamp: number; title: string; prefix: string; body: string; tone: string };

export const detectLanguage = (path: string) => {
    const lower = path.toLowerCase();
    if (lower.endsWith('.tsx') || lower.endsWith('.ts')) return 'typescript';
    if (lower.endsWith('.jsx') || lower.endsWith('.js')) return 'javascript';
    if (lower.endsWith('.py')) return 'python';
    if (lower.endsWith('.json')) return 'json';
    if (lower.endsWith('.md')) return 'markdown';
    if (lower.endsWith('.html')) return 'html';
    if (lower.endsWith('.css')) return 'css';
    if (lower.endsWith('.yml') || lower.endsWith('.yaml')) return 'yaml';
    return 'plaintext';
};
export const normalizeProfile = (value: unknown): 'safe' | 'dev' | 'unrestricted' => (value === 'dev' || value === 'unrestricted' ? value : 'safe');
export const joinRepoPath = (parentPath: string, childName: string) => (parentPath && parentPath !== '.' ? `${parentPath}/${childName}` : childName).replace(/\\/g, '/');

export function sanitizeCloneDir(name: string): string {
    return name.replace(/[^a-zA-Z0-9._-]/g, '').slice(0, 64);
}

export function defaultCloneFolderFromUrl(url: string): string {
    const u = url.trim().replace(/\.git$/i, '').replace(/\/$/, '');
    const part = u.split(/[/:]/).filter(Boolean).pop() || 'repo';
    const cleaned = sanitizeCloneDir(part);
    return cleaned || 'repo';
}
export const parentDirectory = (path: string) => {
    const parts = String(path || '').replace(/\\/g, '/').split('/');
    parts.pop();
    return parts.filter(Boolean).join('/') || '.';
};

/** Directory paths from repo root down to the parent of `filePath` (inclusive of `.`). */
export function dirsAlongPath(filePath: string): string[] {
    const norm = filePath.replace(/\\/g, '/').replace(/^\/+/, '');
    const parts = norm.split('/').filter(Boolean);
    if (parts.length <= 1) return ['.'];
    const out: string[] = ['.'];
    let acc = '';
    for (let i = 0; i < parts.length - 1; i++) {
        acc = acc ? `${acc}/${parts[i]}` : parts[i];
        out.push(acc);
    }
    return out;
}

export function dirsAlongPathWithinRoot(workspaceRoot: string, filePath: string): string[] {
    const w = workspaceRoot === '.' ? '' : workspaceRoot.replace(/\\/g, '/').replace(/^\/+/, '');
    if (!w) return dirsAlongPath(filePath);
    return dirsAlongPath(filePath).filter((p) => p === w || p.startsWith(`${w}/`));
}

export function filterRepoTree(node: agentApi.RepoTreeNode, q: string): agentApi.RepoTreeNode | null {
    const needle = q.trim().toLowerCase();
    if (!needle) return node;
    if (node.type === 'file') {
        return node.name.toLowerCase().includes(needle) || node.path.toLowerCase().includes(needle) ? node : null;
    }
    const rawKids = node.children || [];
    const mapped = rawKids.map((c) => filterRepoTree(c, q)).filter((c): c is agentApi.RepoTreeNode => c != null);
    if (mapped.length) return { ...node, children: mapped };
    if (node.name.toLowerCase().includes(needle) || node.path.toLowerCase().includes(needle)) return { ...node, children: rawKids };
    return null;
}
export const formatTime = (ts?: number) => (ts ? new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--:--:--');
export const statusTone = (status: NodeStatus) => status === 'running' ? 'border-accent/40 bg-accent/10' : status === 'completed' ? 'border-accent-green/40 bg-accent-green/10' : status === 'failed' ? 'border-accent-red/40 bg-accent-red/10' : 'border-surface-4 bg-surface-1';

export function parseSubagentId(message: string, type: string) {
    if (!message) return '';
    if (type === 'subagent.started') return message.match(/Starting\s+([^\s]+)/i)?.[1] || '';
    if (type === 'subagent.completed') return message.match(/(?:Planner|Tester|Verifier|Subagent)\s+([^\s]+)\s+completed/i)?.[1] || '';
    if (type === 'subagent.error') return message.match(/Subagent\s+([^\s]+)\s+failed/i)?.[1] || '';
    return '';
}

export function extractWorkflowNodes(events: agentApi.AgentSpaceEvent[]): FlowNode[] {
    for (let i = events.length - 1; i >= 0; i -= 1) {
        const evt = events[i];
        if (evt.type !== 'run.workflow') continue;
        const rows = Array.isArray((evt.data as { subagents?: unknown })?.subagents) ? (evt.data as { subagents?: Array<Record<string, unknown>> }).subagents || [] : [];
        return rows
            .map((row) => ({
                id: String(row.id || '').trim(),
                role: String(row.role || 'coder'),
                workerLevel: Number(row.worker_level || 1) || 1,
                dependsOn: Array.isArray(row.depends_on) ? row.depends_on.map((dep) => String(dep || '').trim()).filter(Boolean) : [],
                description: String(row.description || ''),
            }))
            .filter((row) => row.id);
    }
    return [];
}

export function buildDiffTab(review: agentApi.AgentSpaceReview, path: string): DiffTab | null {
    const change = (review.changes || []).find((row) => row.path === path) || review.changes?.[0];
    if (!change) return null;
    return {
        id: `review:${review.id}:${path}`,
        type: 'diff',
        title: `${path.split('/').pop() || path} · diff`,
        path,
        reviewId: review.id,
        reviewStatus: review.status,
        original: String(change.old_content || ''),
        modified: String(change.new_content || ''),
    };
}
