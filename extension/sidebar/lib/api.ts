import { loadSettings } from './storage';

const SESSION_ID = 'extension';

export interface ChatRequestOpts {
    message: string;
    mode?: 'chat' | 'vision' | 'math' | 'code' | 'writing';
    history?: { role: string; content: string }[];
    image?: string;
    backendUrl?: string;
    onChunk: (text: string) => void;
    signal?: AbortSignal;
}

async function csrfHeaders(): Promise<Record<string, string>> {
    return { 'Content-Type': 'application/json', 'X-JimAI-CSRF': '1' };
}

async function getBackend(override?: string): Promise<string> {
    if (override) return override.replace(/\/+$/, '');
    const settings = await loadSettings();
    return settings.backendUrl.replace(/\/+$/, '');
}

export async function streamChat(opts: ChatRequestOpts): Promise<string> {
    const backend = await getBackend(opts.backendUrl);
    const body: Record<string, unknown> = {
        message: opts.message,
        mode: opts.mode || 'chat',
        session_id: SESSION_ID,
        history: opts.history || [],
    };
    if (opts.image) {
        body.image = opts.image;
        body.has_image = true;
        body.mode = 'vision';
    }
    const resp = await fetch(`${backend}/api/chat`, {
        method: 'POST',
        headers: await csrfHeaders(),
        body: JSON.stringify(body),
        signal: opts.signal,
    });
    if (!resp.ok || !resp.body) {
        throw new Error(`Backend error ${resp.status}`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let full = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
                const data = JSON.parse(line.slice(6));
                if (data.text) {
                    full += data.text;
                    opts.onChunk(data.text);
                }
            } catch {
                /* skip */
            }
        }
    }
    return full;
}

export async function setSpeedMode(mode: 'fast' | 'balanced' | 'deep', backendUrl?: string): Promise<void> {
    const backend = await getBackend(backendUrl);
    await fetch(`${backend}/api/settings/speed-mode`, {
        method: 'POST',
        headers: await csrfHeaders(),
        body: JSON.stringify({ mode }),
    });
}

export async function checkHealth(backendUrl?: string): Promise<{ ok: boolean; details?: string }> {
    const backend = await getBackend(backendUrl);
    try {
        const resp = await fetch(`${backend}/api/health`);
        if (!resp.ok) return { ok: false, details: `HTTP ${resp.status}` };
        const data = await resp.json();
        return { ok: Boolean(data?.services?.ollama), details: JSON.stringify(data?.services || {}) };
    } catch (err) {
        return { ok: false, details: err instanceof Error ? err.message : String(err) };
    }
}
