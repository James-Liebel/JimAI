import { apiUrl, fetchWithTimeout } from './api';

export type SystemAgentMode = 'supervised' | 'autonomous';

export interface SystemAgentPlanStep {
    step: number;
    tool: string;
    args: Record<string, unknown>;
    description: string;
    depends_on: number[];
    is_destructive: boolean;
}

export interface SystemAgentEvent {
    type: 'plan' | 'step_start' | 'step_result' | 'confirmation_needed' | 'step_error' | 'complete' | 'text';
    data: Record<string, any>;
}

export interface SystemAgentStats {
    cpu_percent: number;
    cpu_cores: number;
    memory_used_gb: number;
    memory_total_gb: number;
    memory_percent: number;
    disk_used_gb: number;
    disk_total_gb: number;
    disk_percent: number;
    gpu?: {
        utilization_percent?: number;
        memory_used_mb?: number;
        memory_total_mb?: number;
        temperature_c?: number;
        name?: string;
    };
}

export interface SystemProcessInfo {
    pid: number;
    name: string;
    status: string;
    cpu_percent: number;
    memory_mb: number;
    create_time: string;
    cmdline: string;
}

export interface SystemFileInfo {
    path: string;
    name: string;
    extension: string;
    size_bytes: number;
    size_human: string;
    modified: string;
    created: string;
    is_dir: boolean;
    line_count?: number | null;
    preview?: string | null;
}

export interface BrowseResponse {
    path: string;
    items: SystemFileInfo[];
    count: number;
    dirs: number;
    files: number;
}

export interface SearchResponse {
    files: SystemFileInfo[];
    total_found: number;
    searched_path: string;
    query: string;
    truncated: boolean;
}

export interface ReadFileResponse {
    path: string;
    content: string;
    total_lines: number;
    total_chars: number;
    truncated: boolean;
    encoding: string;
}

export interface ScreenshotResponse {
    width: number;
    height: number;
    monitor: number;
    timestamp: string;
    saved_to?: string;
    base64?: string;
    media_type?: string;
}

export async function streamSystemAgent(
    task: string,
    sessionId: string,
    mode: SystemAgentMode,
    onEvent: (event: SystemAgentEvent) => void,
): Promise<void> {
    const resp = await fetchWithTimeout(
        apiUrl('/api/system-agent/run'),
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task,
                session_id: sessionId,
                mode,
            }),
        },
        300000,
    );

    if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(text || `System agent run failed: ${resp.status}`);
    }
    if (!resp.body) throw new Error('System agent response body is missing');

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
                const parsed = JSON.parse(line.slice(6)) as SystemAgentEvent;
                onEvent(parsed);
            } catch {
                // Ignore malformed stream chunks.
            }
        }
    }
}

export async function confirmSystemAgent(sessionId: string, approved: boolean): Promise<void> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/confirm'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, approved }),
    });
    if (!resp.ok) throw new Error(`System agent confirmation failed: ${resp.status}`);
}

export async function getSystemAgentStats(): Promise<SystemAgentStats> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/stats'));
    if (!resp.ok) throw new Error(`System stats failed: ${resp.status}`);
    return resp.json();
}

export async function listSystemAgentProcesses(filterName = ''): Promise<SystemProcessInfo[]> {
    const suffix = filterName ? `?filter_name=${encodeURIComponent(filterName)}` : '';
    const resp = await fetchWithTimeout(apiUrl(`/api/system-agent/processes${suffix}`));
    if (!resp.ok) throw new Error(`Process listing failed: ${resp.status}`);
    const data = await resp.json() as { processes: SystemProcessInfo[] };
    return data.processes || [];
}

export async function killSystemProcess(pid: number): Promise<{ killed: boolean; name?: string; reason?: string }> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/processes/kill'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid }),
    });
    if (!resp.ok) throw new Error(`Kill process failed: ${resp.status}`);
    return resp.json();
}

export async function browseSystemFilesystem(path: string): Promise<BrowseResponse> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/browse'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
    });
    if (!resp.ok) throw new Error(`Browse failed: ${resp.status}`);
    return resp.json();
}

export async function searchSystemFilesystem(params: {
    root: string;
    pattern?: string;
    recursive?: boolean;
    extensions?: string[];
    content?: string;
}): Promise<SearchResponse> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/search'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
    });
    if (!resp.ok) throw new Error(`Search failed: ${resp.status}`);
    return resp.json();
}

export async function readSystemFile(path: string, maxChars = 50000): Promise<ReadFileResponse> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/read'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, max_chars: maxChars }),
    });
    if (!resp.ok) throw new Error(`Read failed: ${resp.status}`);
    return resp.json();
}

export async function takeSystemScreenshot(monitor = 1): Promise<ScreenshotResponse> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/screenshot'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monitor, return_base64: true }),
    });
    if (!resp.ok) throw new Error(`Screenshot failed: ${resp.status}`);
    return resp.json();
}

export async function openSystemPath(path: string): Promise<void> {
    const resp = await fetchWithTimeout(apiUrl('/api/system-agent/open-path'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
    });
    if (!resp.ok) throw new Error(`Open path failed: ${resp.status}`);
}
