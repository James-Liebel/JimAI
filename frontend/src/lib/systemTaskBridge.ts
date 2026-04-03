const PENDING_SYSTEM_TASK_KEY = 'jimai_pending_system_task_v1';

export function queueSystemTask(message: string): void {
    if (typeof window === 'undefined') return;
    try {
        window.sessionStorage.setItem(
            PENDING_SYSTEM_TASK_KEY,
            JSON.stringify({ message: message.trim(), createdAt: Date.now() }),
        );
    } catch {
        // ignore
    }
}

export function consumeSystemTask(): string {
    if (typeof window === 'undefined') return '';
    try {
        const raw = window.sessionStorage.getItem(PENDING_SYSTEM_TASK_KEY);
        if (!raw) return '';
        window.sessionStorage.removeItem(PENDING_SYSTEM_TASK_KEY);
        const parsed = JSON.parse(raw) as { message?: string };
        return String(parsed.message || '').trim();
    } catch {
        return '';
    }
}
