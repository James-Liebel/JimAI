import { API_BASE as BASE, apiUrl } from './backendBase';

/** Ollama-backed and other long server jobs often exceed 30s; use for LLM-heavy POSTs. */
export const LLM_HTTP_TIMEOUT_MS = 600_000;

// ── Timeout-aware fetch ───────────────────────────────────────────────

async function fetchWithTimeout(
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

export interface AgentSpaceRunSummary {
    id: string;
    status: string;
    objective: string;
    created_at: number;
    updated_at: number;
    started_at?: number;
    ended_at?: number;
    review_ids: string[];
    snapshot_ids: string[];
    action_count: number;
    error?: string | null;
    team_id?: string | null;
    team_name?: string | null;
    message_count?: number;
    completion_summary?: {
        text?: string;
        status?: string;
        action_count?: number;
        review_count?: number;
        snapshot_count?: number;
        prompt?: string;
        confirmed_suggestions?: string[];
        self_improve_paths?: string[];
        recovered_actions?: number;
        failed_actions?: number;
    } | null;
    /** workspace = Builder / project; jimai = self-improvement & platform changes */
    review_scope?: 'workspace' | 'jimai' | string;
}

export interface AgentSpaceReview {
    id: string;
    run_id: string;
    objective: string;
    status: 'pending' | 'approved' | 'rejected' | 'applied';
    created_at: number;
    updated_at: number;
    diff: string;
    changes?: Array<{
        path: string;
        reason?: string;
        old_content?: string;
        new_content?: string;
        existed_before?: boolean;
    }>;
    summary?: {
        file_count: number;
        added_lines: number;
        removed_lines: number;
        reason_counts: Record<string, number>;
        files: Array<{
            path: string;
            reason: string;
            added: number;
            removed: number;
        }>;
    };
    snapshot_id?: string | null;
    rejection_reason?: string | null;
    metadata?: Record<string, unknown>;
}

export interface ReviewCommitResult {
    review_id: string;
    review_status: string;
    snapshot_id?: string | null;
    commit_id?: string;
    message: string;
    files: string[];
    git_output?: string;
    git_error?: string;
}

export interface AgentSpaceEvent {
    timestamp?: number;
    run_id?: string;
    type: string;
    message?: string;
    data?: Record<string, unknown>;
}

export interface AgentTeamAgent {
    id: string;
    role: string;
    depends_on?: string[];
    actions?: Array<Record<string, unknown>>;
    checks?: string[];
    description?: string;
    model?: string;
}

export interface AgentTeam {
    id?: string;
    name: string;
    description?: string;
    agents: AgentTeamAgent[];
    metadata?: Record<string, unknown>;
}

export interface AgentSkillSummary {
    slug: string;
    name: string;
    description: string;
    tags: string[];
    complexity: number;
    source: string;
    created_at: number;
    updated_at: number;
    match_score?: number;
}

export interface AgentSkillRecord extends AgentSkillSummary {
    metadata?: Record<string, unknown>;
    content: string;
    raw_markdown: string;
    path: string;
}

export interface AgentMessage {
    id: string;
    timestamp: number;
    run_id?: string;
    from: string;
    to?: string;
    channel?: string;
    content: string;
    team_id?: string;
}

export interface ProactiveGoal {
    id: string;
    name: string;
    objective: string;
    interval_seconds: number;
    enabled: boolean;
    next_run_at: number;
    last_run_at?: number | null;
    last_run_id?: string | null;
}

export interface SelfImproveSuggestion {
    id: string;
    text: string;
    source: string;
}

export interface SelfImproveSuggestResponse {
    prompt: string;
    model: string;
    focus: string;
    requires_confirmation: boolean;
    autonomous_notes: string[];
    suggestions: SelfImproveSuggestion[];
}

/** NDJSON events from POST /self-improve/suggest-stream */
export type SelfImproveSuggestStreamEvent =
    | { type: 'meta'; model: string; focus: string }
    | { type: 'action'; stage: string; label: string }
    | { type: 'chunk'; text: string }
    | { type: 'progress'; chars: number }
    | {
          type: 'result';
          prompt?: string;
          model?: string;
          focus?: string;
          requires_confirmation?: boolean;
          autonomous_notes: string[];
          suggestions: SelfImproveSuggestion[];
      }
    | { type: 'stopped'; reason?: string; partial_chars?: number }
    | { type: 'error'; detail: string };

export interface SelfImproveStrengthenResponse {
    strengthened_prompt: string;
    model: string;
}

export interface AppInstanceRow {
    instance_id: string;
    client: string;
    created_at: number;
    last_seen_at: number;
    age_seconds: number;
}

export interface AppInstanceStatus {
    active_instances: number;
    instances: AppInstanceRow[];
    instance_ttl_seconds: number;
    stop_grace_seconds: number;
    pending_stop_at?: number | null;
    managed_ollama_pid?: number | null;
    ollama_running: boolean;
    last_ollama_error?: string;
    last_ollama_start_at?: number;
}

export interface N8nTemplate {
    name: string;
    description: string;
    category: string;
    workflow_json: Record<string, unknown>;
}

export interface AutomationWorkflowSource {
    name: string;
    url: string;
    license?: string;
    why?: string;
}

export interface AutomationWorkflowTemplate {
    name: string;
    description: string;
    category: string;
    graph: Record<string, unknown>;
    public_sources?: AutomationWorkflowSource[];
}

export interface AutomationWorkflowSummary {
    id: string;
    name: string;
    description: string;
    tags: string[];
    created_at: number;
    updated_at: number;
    last_run_at?: number;
    last_run_status?: string;
}

export interface AutomationWorkflowRecord extends AutomationWorkflowSummary {
    graph: Record<string, unknown>;
    public_sources?: AutomationWorkflowSource[];
    last_run_summary?: Record<string, unknown>;
}

export interface AutomationWorkflowStatus {
    engine: string;
    open_source: boolean;
    requires_n8n_runtime: boolean;
    workflow_count: number;
    last_updated_at?: number;
    public_sources?: AutomationWorkflowSource[];
}

export interface AutomationWorkflowRunResult {
    workflow_id: string;
    workflow_name?: string;
    status: string;
    summary?: Record<string, unknown>;
    errors?: string[];
    events?: Array<Record<string, unknown>>;
    output?: Record<string, unknown>;
}

export interface N8nStatus {
    enabled: boolean;
    mode: 'managed' | 'external' | string;
    url: string;
    port: number;
    auto_start: boolean;
    stop_on_shutdown: boolean;
    managed_pid?: number | null;
    managed_running: boolean;
    reachable: boolean;
    last_error?: string;
    last_started_at?: number;
    last_command?: string[];
    install_path?: string;
    started?: boolean;
    stopped?: boolean;
    message?: string;
}

export interface FreeStackServiceStatus {
    key: string;
    name: string;
    url: string;
    reachable?: boolean;
    http_status?: number;
    error?: string;
}

export interface FreeStackStatus {
    enabled: boolean;
    env_path: string;
    env_loaded: boolean;
    generated_at: number;
    services: FreeStackServiceStatus[];
    infra: {
        postgres: string;
        redis: string;
        minio_api: string;
    };
    gotify: {
        enabled: boolean;
        url: string;
        token_configured: boolean;
    };
}

export interface OpenSourceRepo {
    name: string;
    full_name: string;
    url: string;
    description: string;
    stars: number;
    forks: number;
    language: string;
    license_key: string;
    license_spdx: string;
    free_to_use: boolean;
    updated_at: string;
    topics: string[];
}

export interface BrowserSessionSummary {
    session_id: string;
    created_at: number;
    headless: boolean;
    url: string;
    title?: string;
    cursor?: { x: number; y: number };
    scroll?: { x: number; y: number };
}

export interface BrowserLinkInfo {
    href: string;
    text: string;
    x: number;
    y: number;
    width: number;
    height: number;
    visible: boolean;
}

export interface BrowserPageState {
    success: boolean;
    session_id: string;
    url: string;
    title: string;
    cursor: { x: number; y: number };
    scroll: { x: number; y: number };
    viewport: { width: number; height: number };
    document: { width: number; height: number };
    links?: BrowserLinkInfo[];
    image_base64?: string;
    error?: string;
}

export interface BrowserInteractiveField {
    tag: string;
    type: string;
    selector: string;
    name: string;
    id: string;
    placeholder: string;
    label: string;
    aria_label: string;
    required: boolean;
    disabled: boolean;
    visible: boolean;
}

export type BrowserInteractiveResponse = BrowserPageState & {
    fields?: BrowserInteractiveField[];
    count?: number;
};

export interface RepoTreeNode {
    name: string;
    path: string;
    type: 'file' | 'directory';
    children?: RepoTreeNode[];
}

export interface RepoTreeResponse {
    root: string;
    depth: number;
    limit: number;
    scanned: number;
    truncated: boolean;
    tree: RepoTreeNode;
}

export interface ToolShellResult {
    success?: boolean;
    stdout?: string;
    stderr?: string;
    exit_code?: number;
    [key: string]: unknown;
}

export interface ToolWriteResult {
    mode: 'review' | 'direct';
    path?: string;
    snapshot_id?: string;
    review?: AgentSpaceReview;
}

export interface SystemAuditCheck {
    id: string;
    title: string;
    status: 'pass' | 'warn' | 'fail' | 'info';
    summary: string;
    details?: Record<string, unknown>;
}

export interface SystemAuditResponse {
    overall_status: 'pass' | 'warn' | 'fail';
    generated_at: number;
    checks: SystemAuditCheck[];
    summary: {
        pass: number;
        warn: number;
        fail: number;
        total: number;
    };
    metrics?: Record<string, unknown>;
    active_runs?: AgentSpaceRunSummary[];
}

export interface BuilderClarifyResponse {
    questions: string[];
    assumptions: string[];
    draft_objective: string;
    needs_clarification: boolean;
    model: string;
}

export interface BuilderLaunchResponse {
    run: AgentSpaceRunSummary;
    team_name: string;
    team_agent_count: number;
    objective: string;
    open_source_refs?: OpenSourceRepo[];
    used_saved_teams?: string[];
    used_agent_packs?: string[];
    complexity?: {
        level?: string;
        score?: number;
        signals?: string[];
    };
}

export interface BuilderPreviewResponse {
    model: string;
    team_name: string;
    base_agent_count: number;
    team_agent_count: number;
    used_saved_teams: string[];
    used_agent_packs: string[];
    team_agents: Array<{
        id: string;
        role: string;
        worker_level?: number;
        model?: string;
        depends_on: string[];
        description: string;
    }>;
    complexity?: {
        level?: string;
        score?: number;
        signals?: string[];
    };
    option_help: Record<string, string>;
}

export interface ResearchServiceProbe {
    name: string;
    ok: boolean;
    status_code?: number;
    url?: string;
    error?: string;
    model_count?: number;
}

export interface ResearchRunResult {
    ok: boolean;
    answer: string;
    sources: Array<{
        id?: number;
        title: string;
        url: string;
        snippet: string;
        provider?: string;
        engine?: string;
        query?: string;
    }>;
    from_memory?: boolean;
    timings?: Record<string, number>;
    query?: string;
    rewritten_queries?: string[];
    provider_errors?: Record<string, string>;
    raw_mode?: boolean;
}

export interface ResearchStreamEvent {
    type: string;
    message?: string;
    text?: string;
    step?: string;
    status?: string;
    label?: string;
    sources?: ResearchRunResult['sources'];
    services?: Record<string, ResearchServiceProbe>;
    cache_status?: string;
    result_count?: number;
    fetched_pages?: number;
    rewritten_queries?: string[];
    used_rewrite?: boolean;
    from_memory?: boolean;
    score?: number;
    match_percent?: number;
    cached_at?: string;
    cached_age_label?: string;
    ok?: boolean;
    answer?: string;
    timings?: Record<string, number>;
    query?: string;
    provider_errors?: Record<string, string>;
    raw_mode?: boolean;
}

export async function getAgentSpaceStatus() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/status`);
    if (!resp.ok) throw new Error(`status failed: ${resp.status}`);
    return resp.json();
}

export async function getAppInstanceStatus(): Promise<AppInstanceStatus> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/instances`);
    if (!resp.ok) throw new Error(`instances status failed: ${resp.status}`);
    return resp.json();
}

export async function getN8nStatus(): Promise<N8nStatus> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/n8n/status`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `n8n status failed: ${resp.status}`);
    }
    return resp.json();
}

export async function getFreeStackStatus(includeProbe = true): Promise<FreeStackStatus> {
    const params = new URLSearchParams();
    params.set('include_probe', includeProbe ? 'true' : 'false');
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/integrations/free-stack/status?${params.toString()}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `free stack status failed: ${resp.status}`);
    }
    return resp.json();
}

export async function syncFreeStackSettings() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/integrations/free-stack/sync`, {
        method: 'POST',
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `free stack sync failed: ${resp.status}`);
    }
    return resp.json();
}

export async function sendFreeStackTestNotification(payload: {
    title?: string;
    message?: string;
    priority?: number;
}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/integrations/free-stack/notify/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `free stack notify test failed: ${resp.status}`);
    }
    return resp.json();
}

export async function startN8n(force = false): Promise<N8nStatus> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/n8n/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `n8n start failed: ${resp.status}`);
    }
    return resp.json();
}

export async function stopN8n(): Promise<N8nStatus> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/n8n/stop`, { method: 'POST' });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `n8n stop failed: ${resp.status}`);
    }
    return resp.json();
}

export async function installLocalN8n(setAsDefault = true): Promise<N8nStatus> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/n8n/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set_as_default: setAsDefault }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `n8n install failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listN8nTemplates(): Promise<N8nTemplate[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/n8n/templates`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `n8n templates failed: ${resp.status}`);
    }
    const data = await resp.json();
    return Array.isArray(data.templates) ? data.templates : [];
}

export async function getAutomationWorkflowStatus(): Promise<AutomationWorkflowStatus> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows/status`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `workflow status failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listAutomationWorkflowTemplates(): Promise<AutomationWorkflowTemplate[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows/templates`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `workflow templates failed: ${resp.status}`);
    }
    const data = await resp.json();
    return Array.isArray(data.templates) ? data.templates : [];
}

export async function listAutomationWorkflows(limit = 200): Promise<AutomationWorkflowSummary[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows?limit=${Math.max(1, limit)}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `list workflows failed: ${resp.status}`);
    }
    return resp.json();
}

export async function getAutomationWorkflow(workflowId: string): Promise<AutomationWorkflowRecord> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows/${encodeURIComponent(workflowId)}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `get workflow failed: ${resp.status}`);
    }
    return resp.json();
}

export async function upsertAutomationWorkflow(payload: {
    id?: string;
    name: string;
    description?: string;
    tags?: string[];
    graph: Record<string, unknown>;
    public_sources?: AutomationWorkflowSource[];
}): Promise<AutomationWorkflowRecord> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `save workflow failed: ${resp.status}`);
    }
    const data = await resp.json();
    return data.workflow as AutomationWorkflowRecord;
}

export async function deleteAutomationWorkflow(workflowId: string): Promise<{ deleted: boolean }> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows/${encodeURIComponent(workflowId)}`, {
        method: 'DELETE',
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `delete workflow failed: ${resp.status}`);
    }
    return resp.json();
}

export async function runAutomationWorkflow(
    workflowId: string,
    payload: { input?: Record<string, unknown>; max_steps?: number; continue_on_error?: boolean } = {},
): Promise<AutomationWorkflowRunResult> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows/${encodeURIComponent(workflowId)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `run workflow failed: ${resp.status}`);
    }
    return resp.json();
}

export async function importN8nWorkflowJson(payload: {
    workflow_json: Record<string, unknown>;
    name?: string;
    description?: string;
    tags?: string[];
}): Promise<AutomationWorkflowRecord> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/automation/workflows/import/n8n`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `import n8n workflow failed: ${resp.status}`);
    }
    const data = await resp.json();
    return data.workflow as AutomationWorkflowRecord;
}

export async function searchOpenSourceProjects(payload: {
    query: string;
    limit?: number;
    min_stars?: number;
    language?: string;
    include_unknown_license?: boolean;
}): Promise<{
    ok: boolean;
    offline: boolean;
    query: string;
    total_found?: number;
    results: OpenSourceRepo[];
    error?: string;
}> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/oss/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `oss search failed: ${resp.status}`);
    }
    return resp.json();
}

export async function registerAppInstance(payload: {
    instance_id?: string;
    client?: string;
    metadata?: Record<string, unknown>;
} = {}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/instances/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `register instance failed: ${resp.status}`);
    }
    return resp.json();
}

export async function heartbeatAppInstance(payload: {
    instance_id: string;
    client?: string;
    metadata?: Record<string, unknown>;
}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/instances/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `instance heartbeat failed: ${resp.status}`);
    }
    return resp.json();
}

export async function unregisterAppInstance(payload: {
    instance_id: string;
    reason?: string;
}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/instances/unregister`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true,
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `unregister instance failed: ${resp.status}`);
    }
    return resp.json();
}

export async function getPowerState() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/power`);
    if (!resp.ok) throw new Error(`power failed: ${resp.status}`);
    return resp.json();
}

export async function setPowerState(enabled: boolean, releaseGpu?: boolean) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/power`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled, release_gpu_on_off: releaseGpu }),
    });
    if (!resp.ok) throw new Error(`set power failed: ${resp.status}`);
    return resp.json();
}

export async function listRuns(limit = 100): Promise<AgentSpaceRunSummary[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/runs?limit=${limit}`);
    if (!resp.ok) throw new Error(`list runs failed: ${resp.status}`);
    return resp.json();
}

export async function getRun(runId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/runs/${runId}`);
    if (!resp.ok) throw new Error(`get run failed: ${resp.status}`);
    return resp.json();
}

export async function startRun(payload: {
    objective: string;
    autonomous?: boolean;
    team_id?: string;
    team?: Record<string, unknown>;
    allowed_paths?: string[];
    review_gate?: boolean;
    allow_shell?: boolean;
    command_profile?: string;
    max_actions?: number;
    max_seconds?: number;
    subagent_retry_attempts?: number;
    force_research?: boolean;
    required_checks?: string[];
    create_git_checkpoint?: boolean;
    subagents?: Array<Record<string, unknown>>;
    actions?: Array<Record<string, unknown>>;
    review_scope?: 'workspace' | 'jimai';
}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/runs/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `start run failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listRunMessages(runId: string, limit = 200, agentId = '', channel = ''): Promise<AgentMessage[]> {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (agentId) params.set('agent_id', agentId);
    if (channel) params.set('channel', channel);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/runs/${runId}/messages?${params.toString()}`);
    if (!resp.ok) throw new Error(`list run messages failed: ${resp.status}`);
    return resp.json();
}

export async function postRunMessage(
    runId: string,
    payload: { from_agent: string; to_agent?: string; channel?: string; content: string },
): Promise<AgentMessage> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/runs/${runId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`post run message failed: ${resp.status}`);
    return resp.json();
}

export async function stopRun(runId: string, reason = '') {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/runs/${runId}/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
    });
    if (!resp.ok) throw new Error(`stop run failed: ${resp.status}`);
    return resp.json();
}

export function subscribeRunEvents(
    runId: string,
    onEvent: (event: AgentSpaceEvent) => void,
    onError?: (error: Event) => void,
) {
    const source = new EventSource(`${BASE}/api/agent-space/runs/${runId}/events`);
    source.onmessage = (msg) => {
        try {
            const data = JSON.parse(msg.data) as AgentSpaceEvent;
            onEvent(data);
        } catch {
            // ignore malformed chunks
        }
    };
    source.onerror = (err) => {
        if (onError) onError(err);
    };
    return () => source.close();
}

export function subscribeGlobalEvents(
    onEvent: (event: AgentSpaceEvent) => void,
    onError?: (error: Event) => void,
) {
    const source = new EventSource(`${BASE}/api/agent-space/events`);
    source.onmessage = (msg) => {
        try {
            const data = JSON.parse(msg.data) as AgentSpaceEvent;
            onEvent(data);
        } catch {
            // ignore malformed chunks
        }
    };
    source.onerror = (err) => {
        if (onError) onError(err);
    };
    return () => source.close();
}

export async function listReviews(limit = 200): Promise<AgentSpaceReview[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews?limit=${limit}`);
    if (!resp.ok) throw new Error(`list reviews failed: ${resp.status}`);
    return resp.json();
}

export async function getReview(reviewId: string): Promise<AgentSpaceReview> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews/${reviewId}`);
    if (!resp.ok) throw new Error(`get review failed: ${resp.status}`);
    return resp.json();
}

export async function approveReview(reviewId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews/${reviewId}/approve`, { method: 'POST' });
    if (!resp.ok) throw new Error(`approve failed: ${resp.status}`);
    return resp.json();
}

export async function rejectReview(reviewId: string, reason = '') {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews/${reviewId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
    });
    if (!resp.ok) throw new Error(`reject failed: ${resp.status}`);
    return resp.json();
}

export async function applyReview(reviewId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews/${reviewId}/apply`, { method: 'POST' });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `apply failed: ${resp.status}`);
    }
    return resp.json();
}

export async function undoReview(reviewId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews/${reviewId}/undo`, { method: 'POST' });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `undo failed: ${resp.status}`);
    }
    return resp.json();
}

export async function commitReview(
    reviewId: string,
    payload: { message: string; auto_apply?: boolean },
): Promise<ReviewCommitResult> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/reviews/${reviewId}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `commit failed: ${resp.status}`);
    }
    return resp.json();
}

export async function rollback(snapshotId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/rollback/${snapshotId}`, { method: 'POST' });
    if (!resp.ok) throw new Error(`rollback failed: ${resp.status}`);
    return resp.json();
}

export async function listSnapshots(limit = 100) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/snapshots?limit=${limit}`);
    if (!resp.ok) throw new Error(`list snapshots failed: ${resp.status}`);
    return resp.json();
}

export async function getMetrics() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/metrics`);
    if (!resp.ok) throw new Error(`metrics failed: ${resp.status}`);
    return resp.json();
}

export interface ActionLogEntry {
    ts: number;
    run_id: string;
    agent_id: string;
    action: Record<string, unknown>;
    result?: Record<string, unknown>;
}

export async function getActionLogs(limit = 200, runId?: string): Promise<ActionLogEntry[]> {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (runId) params.set('run_id', runId);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/logs/actions?${params.toString()}`);
    if (!resp.ok) throw new Error(`action logs failed: ${resp.status}`);
    return resp.json();
}

export async function rebuildIndex() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/index/rebuild`, { method: 'POST' });
    if (!resp.ok) throw new Error(`rebuild index failed: ${resp.status}`);
    return resp.json();
}

export async function searchIndex(query: string, limit = 20) {
    const encoded = encodeURIComponent(query);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/index/search?q=${encoded}&limit=${limit}`);
    if (!resp.ok) throw new Error(`search index failed: ${resp.status}`);
    return resp.json();
}

export async function recentMemory(limit = 30) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/memory/recent?limit=${limit}`);
    if (!resp.ok) throw new Error(`memory failed: ${resp.status}`);
    return resp.json();
}

export async function searchResearch(query: string, limit = 8) {
    const encoded = encodeURIComponent(query);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/research/search?q=${encoded}&limit=${limit}`);
    if (!resp.ok) throw new Error(`research search failed: ${resp.status}`);
    return resp.json();
}

export async function fetchResearch(url: string) {
    const encoded = encodeURIComponent(url);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/research/fetch?url=${encoded}`);
    if (!resp.ok) throw new Error(`research fetch failed: ${resp.status}`);
    return resp.json();
}

export async function getResearchStatus(): Promise<Record<string, ResearchServiceProbe>> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/research/status`);
    if (!resp.ok) throw new Error(`research status failed: ${resp.status}`);
    return resp.json();
}

export async function runResearch(
    query: string,
    options: { forceLive?: boolean; maxResults?: number; model?: string } = {},
): Promise<ResearchRunResult> {
    const params = new URLSearchParams();
    params.set('q', query);
    params.set('force_live', options.forceLive ? 'true' : 'false');
    params.set('max_results', String(options.maxResults ?? 10));
    if (options.model) params.set('model', options.model);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/research/run?${params.toString()}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `research run failed: ${resp.status}`);
    }
    return resp.json();
}

export async function streamResearch(
    query: string,
    handlers: {
        onEvent: (event: ResearchStreamEvent) => void;
        onDone?: (event: ResearchStreamEvent) => void;
        onError?: (message: string) => void;
    },
    options: { forceLive?: boolean; maxResults?: number; model?: string } = {},
): Promise<void> {
    const params = new URLSearchParams();
    params.set('q', query);
    params.set('force_live', options.forceLive ? 'true' : 'false');
    params.set('max_results', String(options.maxResults ?? 10));
    if (options.model) params.set('model', options.model);

    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/research/stream?${params.toString()}`, {}, 120000);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `research stream failed: ${resp.status}`);
    }
    if (!resp.body) throw new Error('Research stream body is unavailable.');

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
                const event = JSON.parse(line.slice(6)) as ResearchStreamEvent;
                handlers.onEvent(event);
                if (event.type === 'done') handlers.onDone?.(event);
                if (event.type === 'error') handlers.onError?.(String(event.message || 'Research error.'));
            } catch {
                // Ignore malformed stream rows.
            }
        }
    }
}

export interface WorkspaceTextSearchMatch {
    path: string;
    line: number;
    preview: string;
}

export async function workspaceTextSearch(payload: {
    query: string;
    path_prefix?: string;
    max_results?: number;
}): Promise<{ query: string; path_prefix: string; matches: WorkspaceTextSearchMatch[]; count: number }> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/workspace/search-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query: payload.query,
            path_prefix: payload.path_prefix ?? '',
            max_results: payload.max_results ?? 150,
        }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `workspace search failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listRepoTree(
    path = '.',
    depth = 8,
    limit = 10000,
    includeHidden = false,
): Promise<RepoTreeResponse> {
    const params = new URLSearchParams();
    params.set('path', path);
    params.set('depth', String(depth));
    params.set('limit', String(limit));
    params.set('include_hidden', includeHidden ? 'true' : 'false');
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/tools/tree?${params.toString()}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `tools tree failed: ${resp.status}`);
    }
    return resp.json();
}

export async function toolsRead(path: string): Promise<{ path: string; content: string }> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/tools/read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `tools read failed: ${resp.status}`);
    }
    return resp.json();
}

export async function toolsWrite(payload: {
    path: string;
    content: string;
    review_gate?: boolean;
}): Promise<ToolWriteResult> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/tools/write`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `tools write failed: ${resp.status}`);
    }
    return resp.json();
}

export async function createWorkspaceDirectory(path: string): Promise<{ path: string }> {
    const resp = await fetchWithTimeout(`${BASE}/api/workspace/directory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `create directory failed: ${resp.status}`);
    }
    return resp.json();
}

export async function toolsShell(payload: {
    command: string;
    cwd?: string;
    profile?: string;
    timeout?: number;
}): Promise<ToolShellResult> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/tools/shell`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `tools shell failed: ${resp.status}`);
    }
    return resp.json();
}

export async function getSettings() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/settings`);
    if (!resp.ok) throw new Error(`settings failed: ${resp.status}`);
    return resp.json();
}

export async function getSystemAudit(options: {
    include_research_probe?: boolean;
    include_browser_probe?: boolean;
} = {}): Promise<SystemAuditResponse> {
    const params = new URLSearchParams();
    if (typeof options.include_research_probe === 'boolean') {
        params.set('include_research_probe', options.include_research_probe ? 'true' : 'false');
    }
    if (typeof options.include_browser_probe === 'boolean') {
        params.set('include_browser_probe', options.include_browser_probe ? 'true' : 'false');
    }
    const suffix = params.toString() ? `?${params.toString()}` : '';
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/admin/system-audit${suffix}`);
    if (!resp.ok) throw new Error(`system audit failed: ${resp.status}`);
    return resp.json();
}

export async function updateSettings(updates: Record<string, unknown>) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `update settings failed: ${resp.status}`);
    }
    return resp.json();
}

export async function resetAgentSpaceData(payload: {
    clear_reviews?: boolean;
    clear_runs?: boolean;
    clear_snapshots?: boolean;
    clear_logs?: boolean;
    clear_memory?: boolean;
    clear_index?: boolean;
    clear_chats?: boolean;
    clear_runtime?: boolean;
    clear_generated?: boolean;
    clear_self_improvement?: boolean;
    clear_proactive_goals?: boolean;
    clear_teams?: boolean;
    clear_exports?: boolean;
    reset_settings?: boolean;
} = {}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/admin/reset-data`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `reset data failed: ${resp.status}`);
    }
    return resp.json();
}

export async function exportBundle(target_folder: string, include_paths: string[], label = '') {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_folder, include_paths, label }),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `export failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listSkills(limit = 200): Promise<AgentSkillSummary[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills?limit=${Math.max(1, limit)}`);
    if (!resp.ok) throw new Error(`list skills failed: ${resp.status}`);
    return resp.json();
}

export async function getSkill(skillName: string): Promise<AgentSkillRecord> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills/${encodeURIComponent(skillName)}`);
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `get skill failed: ${resp.status}`);
    }
    return resp.json();
}

export async function upsertSkill(payload: {
    name: string;
    description?: string;
    content?: string;
    tags?: string[];
    complexity?: number;
    source?: string;
    metadata?: Record<string, unknown>;
    /** When set, updates this skill folder instead of deriving slug from name only. */
    slug?: string;
}): Promise<AgentSkillRecord> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `upsert skill failed: ${resp.status}`);
    }
    return resp.json();
}

export async function deleteSkill(skillName: string): Promise<{ deleted: boolean }> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills/${encodeURIComponent(skillName)}`, {
        method: 'DELETE',
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `delete skill failed: ${resp.status}`);
    }
    return resp.json();
}

export async function installDefaultSkills(): Promise<{ installed_count: number; installed: AgentSkillSummary[] }> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills/install-defaults`, {
        method: 'POST',
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `install default skills failed: ${resp.status}`);
    }
    return resp.json();
}

export async function autoAddSkills(payload: {
    objective: string;
    max_new_skills?: number;
}): Promise<{
    created_count: number;
    created: AgentSkillSummary[];
    selected: AgentSkillSummary[];
}> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills/auto-add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `auto add skills failed: ${resp.status}`);
    }
    return resp.json();
}

export async function selectSkills(payload: {
    objective: string;
    limit?: number;
    include_context?: boolean;
}): Promise<{
    selected_count: number;
    selected: AgentSkillSummary[];
    context: string;
}> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/skills/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `select skills failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listTeams(limit = 200) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/teams?limit=${limit}`);
    if (!resp.ok) throw new Error(`list teams failed: ${resp.status}`);
    return resp.json();
}

export async function getTeam(teamId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/teams/${teamId}`);
    if (!resp.ok) throw new Error(`get team failed: ${resp.status}`);
    return resp.json();
}

export async function upsertTeam(team: AgentTeam) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/teams`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(team),
    });
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `upsert team failed: ${resp.status}`);
    }
    return resp.json();
}

export async function deleteTeam(teamId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/teams/${teamId}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error(`delete team failed: ${resp.status}`);
    return resp.json();
}

export async function listTeamMessages(teamId: string, limit = 200, runId = '', channel = '') {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (runId) params.set('run_id', runId);
    if (channel) params.set('channel', channel);
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/teams/${teamId}/messages?${params.toString()}`);
    if (!resp.ok) throw new Error(`list team messages failed: ${resp.status}`);
    return resp.json();
}

export async function getProactiveStatus() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/status`);
    if (!resp.ok) throw new Error(`proactive status failed: ${resp.status}`);
    return resp.json();
}

export async function startProactive() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/start`, { method: 'POST' });
    if (!resp.ok) throw new Error(`start proactive failed: ${resp.status}`);
    return resp.json();
}

export async function stopProactive() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/stop`, { method: 'POST' });
    if (!resp.ok) throw new Error(`stop proactive failed: ${resp.status}`);
    return resp.json();
}

export async function tickProactive() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/tick`, { method: 'POST' });
    if (!resp.ok) throw new Error(`tick proactive failed: ${resp.status}`);
    return resp.json();
}

export async function listProactiveGoals(limit = 200): Promise<ProactiveGoal[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/goals?limit=${limit}`);
    if (!resp.ok) throw new Error(`list proactive goals failed: ${resp.status}`);
    return resp.json();
}

export async function createProactiveGoal(payload: {
    name: string;
    objective: string;
    interval_seconds?: number;
    enabled?: boolean;
    run_template?: Record<string, unknown>;
}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`create proactive goal failed: ${resp.status}`);
    return resp.json();
}

export async function updateProactiveGoal(goalId: string, updates: Record<string, unknown>) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/goals/${goalId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    });
    if (!resp.ok) throw new Error(`update proactive goal failed: ${resp.status}`);
    return resp.json();
}

export async function deleteProactiveGoal(goalId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/proactive/goals/${goalId}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error(`delete proactive goal failed: ${resp.status}`);
    return resp.json();
}

export async function suggestSelfImprove(payload: {
    prompt: string;
    max_suggestions?: number;
}): Promise<SelfImproveSuggestResponse> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/self-improve/suggest`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `suggest self improve failed: ${resp.status}`);
    }
    return resp.json();
}

export async function suggestSelfImproveStream(
    payload: { prompt: string; max_suggestions?: number },
    opts: {
        signal?: AbortSignal;
        onEvent: (ev: SelfImproveSuggestStreamEvent) => void;
    },
): Promise<void> {
    const resp = await fetch(`${BASE}/api/agent-space/self-improve/suggest-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-JimAI-CSRF': '1' },
        body: JSON.stringify(payload),
        signal: opts.signal,
    });
    if (!resp.ok) {
        const text = await resp.text();
        let detail = `suggest stream failed: ${resp.status}`;
        try {
            const data = JSON.parse(text) as { detail?: string };
            if (data.detail) detail = String(data.detail);
        } catch {
            if (text) detail = text.slice(0, 240);
        }
        throw new Error(detail);
    }
    const reader = resp.body?.getReader();
    if (!reader) throw new Error('No response body');
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        for (;;) {
            const nl = buffer.indexOf('\n');
            if (nl < 0) break;
            const line = buffer.slice(0, nl).trim();
            buffer = buffer.slice(nl + 1);
            if (!line) continue;
            try {
                opts.onEvent(JSON.parse(line) as SelfImproveSuggestStreamEvent);
            } catch {
                /* ignore malformed line */
            }
        }
    }
    const tail = buffer.trim();
    if (tail) {
        try {
            opts.onEvent(JSON.parse(tail) as SelfImproveSuggestStreamEvent);
        } catch {
            /* ignore */
        }
    }
}

export async function strengthenSelfImprovePrompt(payload: {
    prompt: string;
    /** When set, aborting this signal cancels the request (still bounded by LLM_HTTP_TIMEOUT_MS). */
    signal?: AbortSignal;
}): Promise<SelfImproveStrengthenResponse> {
    const { signal: userSig, prompt } = payload;
    const timerController = new AbortController();
    const tid = setTimeout(() => timerController.abort(), LLM_HTTP_TIMEOUT_MS);
    const merged = new AbortController();
    const onAbort = () => merged.abort();
    timerController.signal.addEventListener('abort', onAbort);
    if (userSig) userSig.addEventListener('abort', onAbort);
    try {
        const resp = await fetch(`${BASE}/api/agent-space/self-improve/strengthen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-JimAI-CSRF': '1' },
            body: JSON.stringify({ prompt }),
            signal: merged.signal,
        });
        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.detail || `strengthen self improve prompt failed: ${resp.status}`);
        }
        return resp.json();
    } catch (err) {
        if (merged.signal.aborted) {
            const e = new Error('Aborted');
            e.name = 'AbortError';
            throw e;
        }
        throw err;
    } finally {
        clearTimeout(tid);
        timerController.signal.removeEventListener('abort', onAbort);
        if (userSig) userSig.removeEventListener('abort', onAbort);
    }
}

export async function runSelfImprove(payload: {
    prompt: string;
    confirmed_suggestions: string[];
    direct_prompt_mode?: boolean;
}) {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/self-improve/run`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `run self improve failed: ${resp.status}`);
    }
    return resp.json();
}

/** NDJSON events from POST /api/agent-space/assist/analyze-stream */
export type AssistStreamEvent =
    | {
          type: 'meta';
          model: string;
          surface: string;
          agents: Array<{ id: string; role: string; depends_on: string[]; description: string }>;
          delegate_objective: string;
      }
    | { type: 'action'; stage: string; label: string }
    | { type: 'chunk'; text: string }
    | { type: 'done' }
    | { type: 'stopped'; reason: string }
    | { type: 'error'; message: string };

export async function planCrossSurfaceAssist(payload: {
    question: string;
    surface?: string;
    context?: string;
    max_agents?: number;
}): Promise<{
    model: string;
    surface: string;
    agents: Array<{ id: string; role: string; depends_on: string[]; description: string }>;
    delegate_objective: string;
}> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/assist/plan`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `assist plan failed: ${resp.status}`);
    }
    return resp.json();
}

export async function streamCrossSurfaceAssist(
    payload: { question: string; surface?: string; context?: string; max_agents?: number },
    opts: { signal?: AbortSignal; onEvent: (ev: AssistStreamEvent) => void },
): Promise<void> {
    const resp = await fetch(`${BASE}/api/agent-space/assist/analyze-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-JimAI-CSRF': '1' },
        body: JSON.stringify(payload),
        signal: opts.signal,
    });
    if (!resp.ok) {
        const text = await resp.text();
        let detail = `assist stream failed: ${resp.status}`;
        try {
            const data = JSON.parse(text) as { detail?: string };
            if (data.detail) detail = String(data.detail);
        } catch {
            if (text) detail = text.slice(0, 240);
        }
        throw new Error(detail);
    }
    const reader = resp.body?.getReader();
    if (!reader) throw new Error('No response body');
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        for (;;) {
            const nl = buffer.indexOf('\n');
            if (nl < 0) break;
            const line = buffer.slice(0, nl).trim();
            buffer = buffer.slice(nl + 1);
            if (!line) continue;
            try {
                opts.onEvent(JSON.parse(line) as AssistStreamEvent);
            } catch {
                /* ignore malformed line */
            }
        }
    }
    const tail = buffer.trim();
    if (tail) {
        try {
            opts.onEvent(JSON.parse(tail) as AssistStreamEvent);
        } catch {
            /* ignore */
        }
    }
}

export async function spawnAssistRun(payload: {
    question: string;
    surface?: string;
    context?: string;
    max_agents?: number;
    autonomous?: boolean;
}): Promise<{
    run: AgentSpaceRunSummary;
    surface: string;
    model: string;
    delegate_objective: string;
    used_saved_teams: string[];
    used_agent_packs: string[];
    complexity: Record<string, unknown>;
    planned_agent_count: number;
    team_agent_count: number;
}> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/assist/spawn-run`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `assist spawn run failed: ${resp.status}`);
    }
    return resp.json();
}

export async function listBrowserSessions(): Promise<BrowserSessionSummary[]> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions`);
    if (!resp.ok) throw new Error(`list browser sessions failed: ${resp.status}`);
    return resp.json();
}

export async function openBrowserSession(payload: {
    url?: string;
    headless?: boolean;
    viewport_width?: number;
    viewport_height?: number;
    user_agent?: string;
    locale?: string;
    timezone_id?: string;
    ignore_https_errors?: boolean;
    slow_mo_ms?: number;
}) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`open browser session failed: ${resp.status}`);
    return resp.json();
}

export async function browserNavigate(sessionId: string, url: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/navigate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
    });
    if (!resp.ok) throw new Error(`browser navigate failed: ${resp.status}`);
    return resp.json();
}

export async function browserClick(sessionId: string, selector: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/click`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector }),
    });
    if (!resp.ok) throw new Error(`browser click failed: ${resp.status}`);
    return resp.json();
}

export async function browserType(
    sessionId: string,
    selector: string,
    text: string,
    pressEnter = false,
    clearFirst = true,
) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector, text, press_enter: pressEnter, clear_first: clearFirst }),
    });
    if (!resp.ok) throw new Error(`browser type failed: ${resp.status}`);
    return resp.json();
}

export async function browserExtract(sessionId: string, selector = 'body', maxChars = 12000) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector, max_chars: maxChars }),
    });
    if (!resp.ok) throw new Error(`browser extract failed: ${resp.status}`);
    return resp.json();
}

export async function browserScreenshot(sessionId: string, fullPage = true) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/screenshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_page: fullPage }),
    });
    if (!resp.ok) throw new Error(`browser screenshot failed: ${resp.status}`);
    return resp.json();
}

export async function browserScrollPage(
    sessionId: string,
    payload: { delta_x?: number; delta_y?: number; position?: string },
): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/scroll-page`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            delta_x: payload.delta_x ?? 0,
            delta_y: payload.delta_y ?? 0,
            position: payload.position ?? '',
        }),
    });
    if (!resp.ok) throw new Error(`browser scroll-page failed: ${resp.status}`);
    return resp.json();
}

export async function browserScrollIntoView(sessionId: string, selector: string): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/scroll-into-view`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector }),
    });
    if (!resp.ok) throw new Error(`browser scroll-into-view failed: ${resp.status}`);
    return resp.json();
}

export async function browserSelect(
    sessionId: string,
    selector: string,
    opts: { value?: string; label?: string },
): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector, value: opts.value ?? '', label: opts.label ?? '' }),
    });
    if (!resp.ok) throw new Error(`browser select failed: ${resp.status}`);
    return resp.json();
}

export async function browserCheck(sessionId: string, selector: string, checked = true): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector, checked }),
    });
    if (!resp.ok) throw new Error(`browser check failed: ${resp.status}`);
    return resp.json();
}

export async function browserPressKey(sessionId: string, key: string, selector = ''): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/press-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, selector }),
    });
    if (!resp.ok) throw new Error(`browser press-key failed: ${resp.status}`);
    return resp.json();
}

export async function browserWaitFor(
    sessionId: string,
    selector: string,
    state = 'visible',
    timeoutMs = 30000,
): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/wait-for`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selector, state, timeout_ms: timeoutMs }),
    });
    if (!resp.ok) throw new Error(`browser wait-for failed: ${resp.status}`);
    return resp.json();
}

export async function getBrowserInteractive(sessionId: string, limit = 80): Promise<BrowserInteractiveResponse> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/browser/sessions/${sessionId}/interactive?limit=${limit}`,
    );
    if (!resp.ok) throw new Error(`browser interactive failed: ${resp.status}`);
    return resp.json();
}

export async function closeBrowserSession(sessionId: string) {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/close`, { method: 'POST' });
    if (!resp.ok) throw new Error(`close browser session failed: ${resp.status}`);
    return resp.json();
}

export async function closeAllBrowserSessions() {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/close-all`, { method: 'POST' });
    if (!resp.ok) throw new Error(`close all browser sessions failed: ${resp.status}`);
    return resp.json();
}

export interface BrowserAgentStep {
    type: 'opened' | 'step' | 'error' | 'done' | 'stopped' | 'keepalive';
    step?: number;
    thought?: string;
    action?: string;
    action_detail?: Record<string, unknown>;
    screenshot?: string;
    url?: string;
    session_id?: string;
    result?: string;
    error?: string;
    reason?: string;
}

export async function openAtlasSession(url = 'https://www.google.com', profileDir = '') {
    const params = new URLSearchParams({ url });
    if (profileDir) params.set('profile_dir', profileDir);
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/browser/atlas/open?${params}`,
        { method: 'POST' },
        60000,
    );
    if (!resp.ok) throw new Error(`atlas open failed: ${resp.status}`);
    return resp.json() as Promise<{ success: boolean; session_id?: string; url?: string; title?: string; error?: string; persistent?: boolean }>;
}

export function runBrowserAgent(
    goal: string,
    url: string,
    opts: { maxSteps?: number; headless?: boolean } = {},
    onEvent: (event: BrowserAgentStep) => void,
    onDone: () => void,
    signal?: AbortSignal,
): void {
    const params = new URLSearchParams({
        goal,
        url,
        max_steps: String(opts.maxSteps ?? 20),
        headless: String(opts.headless ?? false),
    });
    const src = new EventSource(`${BASE}/api/agent-space/browser/agent/run?${params}`);
    if (signal) {
        signal.addEventListener('abort', () => src.close());
    }
    src.onmessage = (e) => {
        try {
            const data: BrowserAgentStep = JSON.parse(e.data);
            if (data.type === 'keepalive') return;
            onEvent(data);
            if (data.type === 'done' || data.type === 'stopped') {
                src.close();
                onDone();
            }
        } catch {
            // skip malformed
        }
    };
    src.onerror = () => {
        src.close();
        onDone();
    };
}

export async function builderClarify(payload: {
    prompt: string;
    context?: string;
    max_questions?: number;
}): Promise<BuilderClarifyResponse> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/builder/clarify`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `builder clarify failed: ${resp.status}`);
    }
    return resp.json();
}

export async function builderLaunch(payload: {
    prompt: string;
    context?: string;
    answers?: Record<string, string>;
    team_name?: string;
    save_team?: boolean;
    auto_agent_packs?: boolean;
    use_saved_teams?: boolean;
    review_gate?: boolean;
    allow_shell?: boolean;
    command_profile?: 'safe' | 'dev' | 'unrestricted';
    required_checks?: string[];
    autonomous?: boolean;
    max_actions?: number;
    max_seconds?: number;
    subagent_retry_attempts?: number;
    continue_on_subagent_failure?: boolean;
    force_research?: boolean;
    create_git_checkpoint?: boolean;
    /** When set, all builder subagents use this Ollama tag for the run (team design + execution). */
    ollama_model?: string;
    /** `auto` assigns a local model per subagent role from installed Ollama models; `manual` uses settings + optional ollama_model. */
    builder_model_mode?: 'auto' | 'manual';
}): Promise<BuilderLaunchResponse> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/builder/launch`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `builder launch failed: ${resp.status}`);
    }
    return resp.json();
}

export async function builderPreview(payload: {
    prompt: string;
    context?: string;
    team_name?: string;
    auto_agent_packs?: boolean;
    use_saved_teams?: boolean;
    ollama_model?: string;
    builder_model_mode?: 'auto' | 'manual';
}): Promise<BuilderPreviewResponse> {
    const resp = await fetchWithTimeout(
        `${BASE}/api/agent-space/builder/preview`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        },
        LLM_HTTP_TIMEOUT_MS,
    );
    if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `builder preview failed: ${resp.status}`);
    }
    return resp.json();
}

export async function getBrowserState(sessionId: string, includeLinks = false, linkLimit = 40): Promise<BrowserPageState> {
    const params = new URLSearchParams();
    params.set('include_links', includeLinks ? 'true' : 'false');
    params.set('link_limit', String(linkLimit));
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/state?${params.toString()}`);
    if (!resp.ok) throw new Error(`browser state failed: ${resp.status}`);
    return resp.json();
}

export async function listBrowserLinks(sessionId: string, limit = 40): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/links?limit=${limit}`);
    if (!resp.ok) throw new Error(`browser links failed: ${resp.status}`);
    return resp.json();
}

export async function browserCursorMove(sessionId: string, x: number, y: number, steps = 1): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/cursor/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x, y, steps }),
    });
    if (!resp.ok) throw new Error(`browser cursor move failed: ${resp.status}`);
    return resp.json();
}

export async function browserCursorClick(
    sessionId: string,
    payload: { x?: number; y?: number; button?: 'left' | 'right' | 'middle'; click_count?: number; delay_ms?: number } = {},
): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/cursor/click`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`browser cursor click failed: ${resp.status}`);
    return resp.json();
}

export async function browserCursorScroll(
    sessionId: string,
    payload: { dx?: number; dy?: number; x?: number; y?: number } = {},
): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/cursor/scroll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`browser cursor scroll failed: ${resp.status}`);
    return resp.json();
}

export async function browserCursorHover(
    sessionId: string,
    payload: { selector?: string; x?: number; y?: number } = {},
): Promise<BrowserPageState> {
    const resp = await fetchWithTimeout(`${BASE}/api/agent-space/browser/sessions/${sessionId}/cursor/hover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`browser cursor hover failed: ${resp.status}`);
    return resp.json();
}
