import type { Source, RoutingDecision, SpeedModeResponse } from './types';
import { API_BASE as BASE, apiUrl } from './backendBase';

// ── Timeout-aware fetch ───────────────────────────────────────────────

export async function fetchWithTimeout(
    url: string,
    options: RequestInit = {},
    timeoutMs = 30000,
): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => {
        controller.abort();
    }, timeoutMs);
    const method = (options?.method || 'GET').toUpperCase();
    const csrfHeaders: Record<string, string> =
        method !== 'GET' && method !== 'HEAD' ? { 'X-JimAI-CSRF': '1' } : {};
    const finalOptions = {
        ...options,
        headers: {
            ...csrfHeaders,
            ...(options?.headers || {}),
        },
        signal: controller.signal,
    };
    try {
        const response = await fetch(url, finalOptions);
        return response;
    } catch (err) {
        if (controller.signal.aborted) {
            throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
        }
        throw err;
    } finally {
        clearTimeout(timer);
    }
}

export { apiUrl };

// ── Speed mode ───────────────────────────────────────────────────────

export async function getSpeedMode(): Promise<SpeedModeResponse> {
    const res = await fetchWithTimeout(`${BASE}/api/settings/speed-mode`);
    return res.json();
}

export async function setSpeedMode(mode: 'fast' | 'balanced' | 'deep'): Promise<SpeedModeResponse> {
    const res = await fetchWithTimeout(`${BASE}/api/settings/speed-mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
    });
    return res.json();
}

export async function streamChat(
    message: string,
    mode: string,
    sessionId: string,
    history: { role: string; content: string }[],
    onChunk: (text: string) => void,
    onSources: (sources: Source[]) => void,
    onRouting: (routing: RoutingDecision) => void,
    onDone: () => void,
    onProgress?: (progress: {
        searchingWeb?: boolean;
        searchStatus?: string;
        browserScreenshotB64?: string;
        browserScreenshotUrl?: string;
    }) => void,
    modelOverride?: string,
    imageBase64?: string,
    skillSlugs?: string[],
    autoSelectSkills?: boolean,
): Promise<void> {
    const body: Record<string, unknown> = {
        message,
        mode,
        session_id: sessionId,
        history,
    };
    if (modelOverride) body.model_override = modelOverride;
    if (imageBase64) {
        body.image = imageBase64;
        body.has_image = true;
    }
    if (skillSlugs && skillSlugs.length > 0) {
        body.skill_slugs = skillSlugs;
    }
    if (autoSelectSkills) {
        body.auto_select_skills = true;
    }

    const resp = await fetchWithTimeout(`${BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    }, 120000);

    if (!resp.ok) throw new Error(`Chat failed: ${resp.status}`);
    if (!resp.body) throw new Error('No response body');

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let doneEmitted = false;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
                const data = JSON.parse(line.slice(6));
                if (typeof onProgress === 'function') {
                    const hasSearch =
                        typeof data.searching_web === 'boolean' || typeof data.search_status === 'string';
                    const hasBrowser =
                        typeof data.browser_screenshot_b64 === 'string' &&
                        data.browser_screenshot_b64.length > 0;
                    if (hasSearch || hasBrowser) {
                        onProgress({
                            searchingWeb:
                                typeof data.searching_web === 'boolean' ? data.searching_web : undefined,
                            searchStatus:
                                typeof data.search_status === 'string' ? data.search_status : undefined,
                            browserScreenshotB64: hasBrowser
                                ? String(data.browser_screenshot_b64)
                                : undefined,
                            browserScreenshotUrl:
                                typeof data.browser_screenshot_url === 'string'
                                    ? data.browser_screenshot_url
                                    : undefined,
                        });
                    }
                }
                if (data.text) onChunk(data.text);
                if (data.done && data.sources) onSources(data.sources);
                if (data.done && data.routing) onRouting({
                    ...data.routing,
                    review: data.review,
                    judge: data.judge,
                    consistency: data.consistency,
                });
                if (data.done && !doneEmitted) {
                    doneEmitted = true;
                    onDone();
                }
            } catch {
                // skip malformed chunks
            }
        }
    }
    // Ensure onDone fires even if the server closes without a done:true event
    if (!doneEmitted) onDone();
}

export async function uploadFile(
    file: File,
    sessionId: string = 'default',
): Promise<{ source: string; chunks_indexed: number }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', sessionId);

    const resp = await fetchWithTimeout(`${BASE}/api/upload`, {
        method: 'POST',
        body: formData,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error((data as { error?: string }).error || `Upload failed: ${resp.status}`);
    if ((data as { success?: boolean }).success === false) {
        throw new Error((data as { error?: string }).error || 'Upload failed');
    }
    return data as { source: string; chunks_indexed: number };
}

export async function uploadUrl(
    url: string,
    sessionId: string = 'default',
): Promise<{ source: string; chunks_indexed: number }> {
    const resp = await fetchWithTimeout(`${BASE}/api/upload/url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, session_id: sessionId }),
    });
    if (!resp.ok) throw new Error(`URL upload failed: ${resp.status}`);
    return resp.json();
}

export async function executeCode(code: string): Promise<{
    stdout: string;
    stderr: string;
    success: boolean;
}> {
    const resp = await fetchWithTimeout(`${BASE}/api/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
    });
    if (!resp.ok) throw new Error(`Execution failed: ${resp.status}`);
    return resp.json();
}

export async function getHealth(): Promise<{
    status: string;
    services: {
        ollama: boolean;
        chromadb: boolean;
        qdrant: boolean;
    };
    ollama_url?: string;
    version?: string;
}> {
    // Always go through the Vite proxy (/health → :8000) so remote clients
    // (phone, Tailscale) don't try to hit 127.0.0.1 on their own device.
    const url = apiUrl('/health');
    const resp = await fetchWithTimeout(url);
    if (!resp.ok) throw new Error(`health ${resp.status}`);
    return resp.json();
}

export async function clearHistory(sessionId: string): Promise<void> {
    await fetchWithTimeout(`${BASE}/api/chat/history/${sessionId}`, { method: 'DELETE' });
}

export async function submitFeedback(
    prompt: string,
    bad_response: string,
    correction: string,
    mode: string,
    thumbs_up: boolean = false,
    note: string = '',
): Promise<void> {
    await fetchWithTimeout(`${BASE}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, bad_response, correction, mode, thumbs_up, note }),
    });
}

export async function getSessions(): Promise<{ sources: string[] }> {
    try {
        const resp = await fetchWithTimeout(`${BASE}/api/chat/history/default`);
        const data = await resp.json();
        return { sources: data.sources || [] };
    } catch {
        return { sources: [] };
    }
}

// ── Persistent chat sessions ─────────────────────────────────────────

export interface SavedChat {
    id: string;
    title: string;
    messages: { id: string; role: string; content: string; mode: string; timestamp: number }[];
    created_at: number;
    updated_at: number;
}

export interface ChatListItem {
    id: string;
    title: string;
    preview: string;
    message_count: number;
    created_at: number;
    updated_at: number;
}

export async function listChats(): Promise<ChatListItem[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/chat/sessions`);
    if (!resp.ok) return [];
    return resp.json();
}

export async function loadChat(chatId: string): Promise<SavedChat | null> {
    const resp = await fetchWithTimeout(`${BASE}/api/chat/sessions/${chatId}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data.error) return null;
    return data;
}

export async function saveChat(
    chatId: string,
    title: string,
    messages: any[],
): Promise<void> {
    await fetchWithTimeout(`${BASE}/api/chat/sessions/${chatId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: chatId, title, messages }),
    });
}

export async function deleteChat(chatId: string): Promise<void> {
    await fetchWithTimeout(`${BASE}/api/chat/sessions/${chatId}`, { method: 'DELETE' });
}
