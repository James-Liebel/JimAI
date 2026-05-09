import { apiUrl } from './backendBase';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(apiUrl(path), {
        ...init,
        headers: {
            'Content-Type': 'application/json',
            'X-JimAI-CSRF': '1',
            ...(init?.headers || {}),
        },
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`${res.status} ${res.statusText} ${text}`.trim());
    }
    if (res.status === 204) return null as T;
    return (await res.json()) as T;
}

export type EpisodeRecord = {
    id: string;
    timestamp: number;
    run_id: string;
    agent_id: string;
    event: string;
    outcome: string;
    summary: string;
    metadata?: Record<string, unknown>;
};

export type SkillEntry = {
    id: string;
    name: string;
    description: string;
    objective: string;
    artifact_type: string;
    artifact: string;
    tags: string[];
    success_count: number;
    use_count: number;
    last_used_at: number;
    verifier_score: number;
    created_at: number;
    updated_at: number;
};

export type ReflectionTrace = {
    id: string;
    created_at: number;
    run_id: string;
    agent_id: string;
    objective: string;
    attempt: number;
    failure_reason: string;
    lesson: string;
};

export type HeartbeatJob = {
    id: string;
    name: string;
    objective: string;
    interval_seconds: number;
    next_fire_at: number;
    last_fired_at: number;
    fire_count: number;
    enabled: boolean;
    one_shot: boolean;
    last_error: string;
};

export type HeartbeatStatus = {
    running: boolean;
    bound: boolean;
    job_count: number;
    enabled_count?: number;
    tick_interval_seconds?: number;
    last_tick_at?: number;
    last_tick_fired?: number;
    last_error?: string;
};

export const memoryStats = () => request<Record<string, number>>('/api/autonomy/memory/stats');
export const memoryRecent = (limit = 50) =>
    request<{ items: EpisodeRecord[] }>(`/api/autonomy/memory/recent?limit=${limit}`);
export const memorySearch = (query: string, limit = 5) =>
    request<{ results: (EpisodeRecord & { score: number })[] }>('/api/autonomy/memory/search', {
        method: 'POST',
        body: JSON.stringify({ query, limit }),
    });
export const memoryConsolidate = (max_per_run = 3) =>
    request<{ consolidated: number }>('/api/autonomy/memory/consolidate', {
        method: 'POST',
        body: JSON.stringify({ max_per_run }),
    });

export const skillStats = () => request<Record<string, unknown>>('/api/autonomy/skills/stats');
export const skillList = (limit = 200) =>
    request<{ items: SkillEntry[] }>(`/api/autonomy/skills?limit=${limit}`);
export const skillRetrieve = (objective: string, limit = 5) =>
    request<{ results: (SkillEntry & { score: number })[] }>('/api/autonomy/skills/retrieve', {
        method: 'POST',
        body: JSON.stringify({ objective, limit }),
    });
export const skillDelete = (id: string) =>
    request<{ ok: boolean }>(`/api/autonomy/skills/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const reflectionStats = () => request<Record<string, unknown>>('/api/autonomy/reflections/stats');
export const reflectionLookup = (objective: string, limit = 4) =>
    request<{ lessons: ReflectionTrace[] }>('/api/autonomy/reflections/lookup', {
        method: 'POST',
        body: JSON.stringify({ objective, limit }),
    });

export const heartbeatStatus = () => request<HeartbeatStatus>('/api/autonomy/heartbeat/status');
export const heartbeatJobs = () =>
    request<{ items: HeartbeatJob[] }>('/api/autonomy/heartbeat/jobs');
export const heartbeatStart = () => request<HeartbeatStatus>('/api/autonomy/heartbeat/start', { method: 'POST' });
export const heartbeatStop = () => request<HeartbeatStatus>('/api/autonomy/heartbeat/stop', { method: 'POST' });
export const heartbeatTick = () =>
    request<{ due: number; fired: number; errors: unknown[] }>('/api/autonomy/heartbeat/tick', { method: 'POST' });
export const heartbeatAddJob = (input: {
    name: string;
    objective: string;
    interval_seconds?: number;
    one_shot?: boolean;
    enabled?: boolean;
    first_fire_in_seconds?: number;
}) =>
    request<HeartbeatJob>('/api/autonomy/heartbeat/jobs', {
        method: 'POST',
        body: JSON.stringify(input),
    });
export const heartbeatDeleteJob = (id: string) =>
    request<{ ok: boolean }>(`/api/autonomy/heartbeat/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });
