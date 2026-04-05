export type Mode = 'math' | 'code' | 'chat' | 'vision' | 'writing' | 'data' | 'finance';

export type SpeedMode = 'fast' | 'balanced' | 'deep';

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

export interface ConsistencyResult {
    confidence: 'high' | 'medium' | 'low' | 'single_shot';
    agreement_rate?: number;
    n_samples?: number;
    disagreements?: string[];
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

export const MODEL_OPTIONS = [
    { value: '', label: 'Auto (recommended)', color: '' },
    { value: 'math', label: 'Math model', color: 'border-accent-blue' },
    { value: 'code', label: 'Code model', color: 'border-accent-green' },
    { value: 'chat', label: 'Chat model', color: 'border-surface-4' },
    { value: 'vision', label: 'Vision model', color: 'border-accent-purple' },
    { value: 'writing', label: 'Chat (writing style)', color: 'border-accent-amber' },
    { value: 'data', label: 'Data science model', color: 'border-accent-green' },
    { value: 'finance', label: 'Finance model', color: 'border-accent-blue' },
] as const;
