export type Mode = 'math' | 'code' | 'chat' | 'vision' | 'writing' | 'data' | 'finance' | 'browser';

export type SpeedMode = 'turbo' | 'fast' | 'balanced' | 'deep';

export interface SpeedModeResponse {
    mode: SpeedMode;
    warning?: string;
    models: Record<string, string | { model: string; display: object }>;
}

export interface Source {
    text: string;
    source: string;
    score: number;
    url?: string;
}

export interface JudgeResult {
    ran: boolean;
    passed: boolean;
    confidence: 'high' | 'medium' | 'low';
    issues: string[];
    suggestions: string[];
    judge_model: string;
    was_revised: boolean;
}

export interface ToolErrorDetail {
    tool: string;
    kind: 'timeout' | 'runtime' | 'invalid_input';
    message: string;
}

export interface ConsistencyResult {
    confidence: 'high' | 'medium' | 'low' | 'single_shot';
    agreement_rate?: number;
    n_samples?: number;
    disagreements?: string[];
    /** Which domain self-consistency ran for (math | finance) */
    domain?: string;
}

export interface RoutingDecision {
    primary_model: string;
    primary_role: string;
    pipeline: string[];
    pipeline_roles: string[];
    is_hybrid: boolean;
    confidence: number;
    reasoning: string;
    detected_domains: string[];
    speed_mode: string;
    manual_override: string | null;
    /** Reviewer verdict (CONFIRMED / CORRECTED) when layering is enabled */
    review?: string;
    /** Compare mode: two models run, then judge */
    compare_models?: string[];
    compare_pipeline_roles?: string[];
    judge_model?: string;
    /** When set, NPU/second instance was used (e.g. "model_b", "review") */
    npu_used_for?: string;
    /** Model-as-judge quality verification result */
    judge?: JudgeResult;
    /** Math self-consistency result (agreement rate, n_samples) */
    consistency?: ConsistencyResult;
    /** Auto web research diagnostics */
    auto_web_research_attempted?: boolean;
    auto_web_research_ok?: boolean;
    auto_web_research_results?: number;
    auto_web_research_offline?: boolean;
    auto_web_research_queries?: string[];
    auto_web_research_fetched_pages?: number;
    auto_web_research_domain_count?: number;
    auto_web_research_query_count?: number;
    auto_web_research_status?: string;
    /** Headless browser screenshot path (Chat API) */
    chat_browser_capture?: boolean;
    chat_browser_url?: string | null;
    /** Auto tools that ran for this turn (code_exec, math, sysinfo, datetime, calculator) */
    tools_used?: string[];
    /** Tool failures with explicit errors, e.g. ["git: not a repo", "file_read: No path detected"] */
    tool_errors?: string[];
    /** Structured tool failures with kind ('timeout' | 'runtime' | 'invalid_input') for richer UI affordances */
    tool_error_details?: ToolErrorDetail[];
    /** Per-request model context (this chat only, after windowing) */
    context_window_messages?: number;
    context_window_chars?: number;
    cross_chat_memory_active?: boolean;
    rolling_summary_active?: boolean;
}

export interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    mode: Mode;
    timestamp: number;
    sources?: Source[];
    isStreaming?: boolean;
    routing?: RoutingDecision;
    imageBase64?: string;
    /** Ephemeral: headless browser capture for this assistant turn (not persisted in saveChat) */
    browserScreenshotBase64?: string;
    browserScreenshotUrl?: string;
}

export interface ChatState {
    messages: Message[];
    isStreaming: boolean;
    sessionId: string;
    mode: Mode;
    activeFiles: string[];
}

export interface AgentUpdate {
    agent: string;
    step: string;
    status: 'running' | 'done' | 'error';
    detail?: string;
    final_response?: string;
    keepalive?: boolean;
}

/**
 * `label` names the model in the dropdown, where there is room to be explicit.
 * `short` is what the chip shows once one is picked — the chip sits on one line
 * next to the routing preview, so a long label would push it off a phone screen.
 */
export const MODEL_OPTIONS = [
    { value: '', label: 'Auto (recommended)', short: 'Auto', color: '' },
    { value: 'math', label: 'Math model', short: 'Math', color: 'border-accent-blue' },
    { value: 'code', label: 'Code model', short: 'Code', color: 'border-accent-green' },
    { value: 'chat', label: 'Chat model', short: 'Chat', color: 'border-surface-4' },
    { value: 'vision', label: 'Vision model', short: 'Vision', color: 'border-accent-purple' },
    { value: 'writing', label: 'Chat (writing style)', short: 'Writing', color: 'border-accent-amber' },
    { value: 'data', label: 'Data science model', short: 'Data', color: 'border-accent-green' },
    { value: 'finance', label: 'Finance model', short: 'Finance', color: 'border-accent-blue' },
    { value: 'uncensored-12b', label: 'Gemma 4 12B — uncensored', short: 'Gemma 12B', color: 'border-accent-purple' },
    { value: 'uncensored-27b', label: 'Qwen3.8 27B — uncensored', short: 'Qwen 27B', color: 'border-accent-purple' },
    { value: 'uncensored-vl', label: 'Qwen3-VL 8B — uncensored vision', short: 'Qwen VL 8B', color: 'border-accent-purple' },
] as const;
