/**
 * Utility functions for the frontend.
 */

export function cn(...classes: (string | boolean | undefined | null)[]): string {
    return classes.filter(Boolean).join(' ');
}

/**
 * Convert LaTeX delimiters from \(...\) / \[...\] to $...$ / $$...$$ so
 * remark-math + rehype-katex can render them. Also handles common model
 * output patterns like bare \frac, \int etc. wrapped in plain parentheses.
 */
export function preprocessLatex(content: string): string {
    let result = content;

    // \[...\] → $$...$$ (display math — must come before inline)
    result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_match, inner) => {
        return `$$${inner}$$`;
    });

    // \(...\) → $...$ (inline math)
    result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_match, inner) => {
        return `$${inner}$`;
    });

    return result;
}

export function formatTimestamp(ts: number): string {
    return new Date(ts).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
    });
}

export function truncate(text: string, maxLen: number): string {
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + '…';
}

export function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result as string;
            // Strip the data:image/...;base64, prefix
            const b64 = result.split(',')[1] || result;
            resolve(b64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

export type SharedWorkspaceDraft = {
    teamName?: string;
    savedTeamId?: string;
    savedTeamName?: string;
    objective?: string;
    prompt?: string;
    context?: string;
    selectedSkills?: Array<{ slug: string; name: string }>;
    lastRunId?: string;
    lastRunStatus?: string;
    lastRunObjective?: string;
    updatedAt?: number;
};

const SHARED_WORKSPACE_DRAFT_KEY = 'jimai_shared_workspace_draft_v1';

export function readSharedWorkspaceDraft(): SharedWorkspaceDraft {
    if (typeof window === 'undefined') return {};
    try {
        const raw = window.localStorage.getItem(SHARED_WORKSPACE_DRAFT_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw) as SharedWorkspaceDraft;
        return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
        return {};
    }
}

export function writeSharedWorkspaceDraft(patch: SharedWorkspaceDraft): SharedWorkspaceDraft {
    const current = readSharedWorkspaceDraft();
    const next: SharedWorkspaceDraft = {
        ...current,
        ...patch,
        updatedAt: Date.now(),
    };
    if (typeof window !== 'undefined') {
        try {
            window.localStorage.setItem(SHARED_WORKSPACE_DRAFT_KEY, JSON.stringify(next));
        } catch {
            // ignore storage failures
        }
    }
    return next;
}
