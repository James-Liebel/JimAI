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

export type SecurityOverview = {
    prompt_shield: Record<string, unknown>;
    secret_scanner: Record<string, unknown>;
    tool_gate: Record<string, unknown>;
    egress_guardian: Record<string, unknown>;
    behavior_monitor: Record<string, unknown>;
    supply_chain_sentinel: Record<string, unknown>;
};

export type ShieldVerdict = {
    id: string;
    timestamp: number;
    action: 'allow' | 'flag' | 'block';
    severity: 'low' | 'medium' | 'high' | 'critical';
    reasons: string[];
    pattern_matches: { rule: string; severity: string; snippet?: string }[];
    guardrail_model_verdict?: string;
};

export type SecretFinding = {
    rule: string;
    description: string;
    match: string;
    severity: string;
    line: number;
    metadata?: Record<string, unknown>;
};

export type EgressVerdict = {
    allowed: boolean;
    url: string;
    host: string;
    reason?: string;
    matched_rule?: string;
};

export type ToolPolicy = {
    tool: string;
    allowed_agents: string[];
    required_arg_keys: string[];
    forbidden_arg_keys: string[];
    max_arg_chars: number;
    rate_limit_per_minute: number;
    secret_scan: boolean;
    description: string;
};

export type SupplyChainReport = {
    started_at: number;
    ended_at?: number;
    duration_seconds?: number;
    findings: {
        package: string;
        ecosystem: string;
        installed_version: string;
        cve_ids: string[];
        advisory_ids: string[];
        severity: string;
        summary: string;
        fix_versions: string[];
    }[];
    ecosystems: Record<string, Record<string, unknown>>;
    errors?: { tool: string; error?: string; stderr?: string; rc?: number }[];
};

export const securityOverview = () => request<SecurityOverview>('/api/security/overview');

export const shieldCheck = (text: string, opts?: { source?: string; useGuardrail?: boolean }) =>
    request<ShieldVerdict>('/api/security/shield/check', {
        method: 'POST',
        body: JSON.stringify({
            text,
            source: opts?.source || 'manual_test',
            use_guardrail: opts?.useGuardrail,
        }),
    });

export const shieldSetGuardrailModel = (model: string | null) =>
    request<{ guardrail_model: string }>('/api/security/shield/guardrail-model', {
        method: 'POST',
        body: JSON.stringify({ model: model || '' }),
    });

export const secretsScan = (text: string) =>
    request<{ count: number; findings: SecretFinding[] }>('/api/security/secrets/scan', {
        method: 'POST',
        body: JSON.stringify({ text }),
    });

export const toolGatePolicies = () =>
    request<{ policies: ToolPolicy[] }>('/api/security/tool-gate/policies');

export const toolGateAudit = (limit = 200) =>
    request<{ items: { id: string; timestamp: number; agent_id: string; tool: string; decision: string; reasons: string[] }[] }>(
        `/api/security/tool-gate/audit?limit=${limit}`,
    );

export const egressCheck = (url: string) =>
    request<EgressVerdict>('/api/security/egress/check', {
        method: 'POST',
        body: JSON.stringify({ url }),
    });

export const egressAllowDomain = (domain: string) =>
    request<{ ok: boolean }>('/api/security/egress/allow', {
        method: 'POST',
        body: JSON.stringify({ domain }),
    });

export const supplyChainLatest = () =>
    request<SupplyChainReport>('/api/security/supply-chain/latest');

export const supplyChainScan = () =>
    request<SupplyChainReport>('/api/security/supply-chain/scan', { method: 'POST' });

export const supplyChainBaseline = () =>
    request<{ keys: string[] }>('/api/security/supply-chain/baseline', { method: 'POST' });

export const supplyChainDiff = () =>
    request<{
        based_on_latest_at: number;
        new_count: number;
        resolved_count: number;
        new_findings: SupplyChainReport['findings'];
        resolved_keys: string[];
    }>('/api/security/supply-chain/diff');
