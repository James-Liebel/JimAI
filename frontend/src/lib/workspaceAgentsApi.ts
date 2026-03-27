import { apiUrl } from './backendBase';

function csrf(method: string): Record<string, string> {
    const m = method.toUpperCase();
    return m !== 'GET' && m !== 'HEAD' ? { 'X-JimAI-CSRF': '1' } : {};
}

async function j<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(apiUrl(path), {
        ...init,
        headers: {
            'Content-Type': 'application/json',
            ...csrf(init?.method || 'GET'),
            ...(init?.headers || {}),
        },
    });
    if (!res.ok) {
        const err = await res.text();
        throw new Error(err || res.statusText);
    }
    return res.json() as Promise<T>;
}

export interface WorkspaceAgent {
    id: string;
    slug: string;
    name: string;
    role: string;
    avatar: string;
    model: string;
    system_prompt: string;
    skills: string[];
    memory_enabled: boolean;
    tools: string[];
    team_ids: string[];
    created_at: string;
    updated_at: string;
    status?: 'idle' | 'running' | 'error';
    skill_files?: SkillFileMeta[];
}

export interface SkillFileMeta {
    name: string;
    slug: string;
    path: string;
    preview: string;
    modified_at: string;
    size_bytes: number;
}

export interface WorkspaceTeam {
    id: string;
    name: string;
    description: string;
    agent_ids: string[];
    workflow: 'sequential' | 'parallel' | 'orchestrated';
    shared_skills: string[];
    created_at: string;
    updated_at: string;
}

export async function listWorkspaceAgents(): Promise<WorkspaceAgent[]> {
    const data = await j<{ agents: WorkspaceAgent[] }>('/api/agents');
    return data.agents;
}

export async function getWorkspaceAgent(id: string): Promise<WorkspaceAgent> {
    return j<WorkspaceAgent>(`/api/agents/${id}`);
}

export async function createWorkspaceAgent(body: {
    name: string;
    role: string;
    slug?: string;
    avatar?: string;
    model?: string;
    system_prompt?: string;
}): Promise<WorkspaceAgent> {
    return j<WorkspaceAgent>('/api/agents', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateWorkspaceAgent(
    id: string,
    body: Partial<{
        name: string;
        role: string;
        slug: string;
        avatar: string;
        model: string;
        system_prompt: string;
        memory_enabled: boolean;
        tools: string[];
        skills: string[];
        status: string;
    }>,
): Promise<WorkspaceAgent> {
    return j<WorkspaceAgent>(`/api/agents/${id}`, { method: 'PUT', body: JSON.stringify(body) });
}

export async function deleteWorkspaceAgent(id: string): Promise<void> {
    await j(`/api/agents/${id}`, { method: 'DELETE' });
}

export async function listOllamaModels(): Promise<string[]> {
    const data = await j<{ models: string[] }>('/api/agents/models');
    return data.models;
}

export async function listAgentSkills(agentId: string): Promise<SkillFileMeta[]> {
    const data = await j<{ skills: SkillFileMeta[] }>(`/api/agents/${agentId}/skills`);
    return data.skills;
}

export async function generateSkill(
    agentId: string,
    body: { skill_name: string; skill_description?: string; example_task?: string },
): Promise<{ markdown: string; suggested_slug: string }> {
    return j(`/api/agents/${agentId}/skills/generate`, {
        method: 'POST',
        body: JSON.stringify(body),
    });
}

export async function saveSkill(
    agentId: string,
    skillSlug: string,
    content: string,
    skill_slug?: string,
): Promise<void> {
    await j(`/api/agents/${agentId}/skills/${skillSlug}`, {
        method: 'PUT',
        body: JSON.stringify({ content, skill_slug }),
    });
}

export async function getSkillRaw(agentId: string, skillSlug: string): Promise<string> {
    const data = await j<{ content: string }>(`/api/agents/${agentId}/skills/${skillSlug}/raw`);
    return data.content;
}

export async function deleteSkillFile(agentId: string, skillSlug: string): Promise<void> {
    await j(`/api/agents/${agentId}/skills/${skillSlug}`, { method: 'DELETE' });
}

export async function listTeams(): Promise<WorkspaceTeam[]> {
    const data = await j<{ teams: WorkspaceTeam[] }>('/api/teams');
    return data.teams;
}

export async function createTeam(body: {
    name: string;
    description?: string;
    agent_ids?: string[];
    workflow?: string;
    shared_skills?: string[];
}): Promise<WorkspaceTeam> {
    return j<WorkspaceTeam>('/api/teams', { method: 'POST', body: JSON.stringify(body) });
}

export async function updateTeam(
    id: string,
    body: Partial<{
        name: string;
        description: string;
        agent_ids: string[];
        workflow: string;
        shared_skills: string[];
    }>,
): Promise<WorkspaceTeam> {
    return j<WorkspaceTeam>(`/api/teams/${id}`, { method: 'PUT', body: JSON.stringify(body) });
}

export async function deleteTeam(id: string): Promise<void> {
    await j(`/api/teams/${id}`, { method: 'DELETE' });
}

export async function streamAgentChat(
    agentId: string,
    message: string,
    history: { role: string; content: string }[],
    onChunk: (text: string) => void,
    onDone: () => void,
): Promise<void> {
    const res = await fetch(apiUrl(`/api/agents/${agentId}/chat`), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...csrf('POST'),
        },
        body: JSON.stringify({ message, history }),
    });
    if (!res.ok) throw new Error(await res.text());
    const reader = res.body?.getReader();
    if (!reader) throw new Error('No body');
    const dec = new TextDecoder();
    let buf = '';
    let finished = false;
    const finishOnce = () => {
        if (finished) return;
        finished = true;
        onDone();
    };
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
                const data = JSON.parse(line.slice(6));
                if (data.text) onChunk(data.text);
                if (data.done) finishOnce();
            } catch {
                /* skip */
            }
        }
    }
    finishOnce();
}

export async function streamTeamRun(
    teamId: string,
    task: string,
    onLine: (obj: Record<string, unknown>) => void,
): Promise<void> {
    const res = await fetch(apiUrl(`/api/teams/${teamId}/run`), {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...csrf('POST'),
        },
        body: JSON.stringify({ task }),
    });
    if (!res.ok) throw new Error(await res.text());
    const reader = res.body?.getReader();
    if (!reader) throw new Error('No body');
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
                onLine(JSON.parse(line.slice(6)) as Record<string, unknown>);
            } catch {
                /* skip */
            }
        }
    }
}
