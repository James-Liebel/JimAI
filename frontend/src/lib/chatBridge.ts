const PENDING_CHAT_PROMPT_KEY = 'jimai_pending_chat_prompt_v1';

export function queueChatPrompt(message: string): void {
    if (typeof window === 'undefined') return;
    try {
        window.localStorage.setItem(
            PENDING_CHAT_PROMPT_KEY,
            JSON.stringify({ message, createdAt: Date.now() }),
        );
    } catch {
        // ignore storage failures
    }
}

export function consumeQueuedChatPrompt(): string {
    if (typeof window === 'undefined') return '';
    try {
        const raw = window.localStorage.getItem(PENDING_CHAT_PROMPT_KEY);
        if (!raw) return '';
        window.localStorage.removeItem(PENDING_CHAT_PROMPT_KEY);
        const parsed = JSON.parse(raw) as { message?: string };
        return String(parsed.message || '');
    } catch {
        return '';
    }
}
