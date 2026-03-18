import type { RoutingDecision } from '../lib/types';

interface Props {
    routing: RoutingDecision;
}

const ROLE_STYLES: Record<string, string> = {
    math: 'bg-accent-blue/15 text-accent-blue border-accent-blue/25',
    code: 'bg-accent-green/15 text-accent-green border-accent-green/25',
    chat: 'bg-surface-4/50 text-text-secondary border-surface-4',
    vision: 'bg-accent-purple/15 text-accent-purple border-accent-purple/25',
    writing: 'bg-accent-amber/15 text-accent-amber border-accent-amber/25',
    data: 'bg-accent-green/15 text-accent-green border-accent-green/25',
    finance: 'bg-accent-blue/15 text-accent-blue border-accent-blue/25',
    override: 'bg-surface-4/50 text-text-secondary border-surface-4',
    deep: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
};

function modelShortName(model: string): string {
    if (model.includes('deepseek-r1')) return 'R1-14B';
    if (model.includes('qwen2.5-coder:14b')) return 'Coder-14B';
    if (model.includes('qwen2.5-coder:7b')) return 'Coder-7B';
    if (model.includes('qwen3:8b')) return 'Qwen3-8B';
    if (model.includes('qwen2.5vl')) return 'VL-7B';
    if (model.includes('qwen2-math')) return 'Math-7B';
    if (model.includes('qwen2.5:32b')) return '32B';
    return model.split(':')[0];
}

function speedSuffix(speedMode: string | undefined): string {
    if (speedMode === 'fast') return ' (fast)';
    if (speedMode === 'deep') return ' (deep)';
    return '';
}

export default function RouterBadge({ routing }: Props) {
    const {
        primary_model,
        primary_role,
        pipeline,
        pipeline_roles,
        is_hybrid,
        reasoning,
        speed_mode,
        manual_override,
        compare_models,
        judge_model,
        npu_used_for,
        auto_web_research_attempted,
        auto_web_research_ok,
        auto_web_research_results,
        auto_web_research_offline,
        auto_web_research_domain_count,
    } = routing;

    const role = primary_role || 'chat';
    const suffix = speedSuffix(speed_mode);

    if (compare_models && compare_models.length >= 2 && judge_model) {
        return (
            <div className="flex items-center gap-1 group/badge relative flex-wrap">
                <span className="text-[10px] text-text-muted">Compare:</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] border ${ROLE_STYLES.chat}`}>
                    {modelShortName(compare_models[0])}
                </span>
                <span className="text-[9px] text-text-muted">vs</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] border ${ROLE_STYLES.chat}`}>
                    {modelShortName(compare_models[1])}{npu_used_for === 'model_b' && <span className="ml-0.5 text-[9px] text-amber-400">NPU</span>}
                </span>
                <span className="text-[9px] text-text-muted">→</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] border ${ROLE_STYLES.chat}`}>
                    {modelShortName(judge_model)}
                </span>
                <Tooltip reasoning="Two models answered; judge chose/synthesized the response." />
            </div>
        );
    }

    if (is_hybrid && pipeline.length > 1) {
        const roles = pipeline_roles || pipeline;
        return (
            <div className="flex items-center gap-1 group/badge relative">
                {pipeline.map((model, i) => {
                    const r = roles[i] || 'chat';
                    return (
                        <span key={`${model}-${i}`} className="flex items-center gap-0.5">
                            {i > 0 && <span className="text-[9px] text-text-muted mx-0.5">→</span>}
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] border ${ROLE_STYLES[r] || ROLE_STYLES.chat}`}>
                                {modelShortName(model)}
                            </span>
                        </span>
                    );
                })}
                <Tooltip reasoning={reasoning + suffix} />
            </div>
        );
    }

    return (
        <div className="group/badge relative inline-flex items-center gap-1.5">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] border ${ROLE_STYLES[role] || ROLE_STYLES.chat}`}>
                {manual_override && (
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor" className="opacity-60">
                        <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
                    </svg>
                )}
                {modelShortName(primary_model)}{suffix}
            </span>
            {auto_web_research_attempted && (
                <span
                    className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] border ${
                        auto_web_research_ok
                            ? 'border-accent-green/30 text-accent-green bg-accent-green/10'
                            : auto_web_research_offline
                                ? 'border-accent-red/30 text-accent-red bg-accent-red/10'
                                : 'border-amber-500/30 text-amber-400 bg-amber-500/10'
                    }`}
                >
                    {auto_web_research_ok
                        ? `Web ${Math.max(0, Number(auto_web_research_results || 0))}${Number(auto_web_research_domain_count || 0) > 0 ? ` • ${Math.max(0, Number(auto_web_research_domain_count || 0))} sites` : ''}`
                        : auto_web_research_offline
                            ? 'Web offline'
                            : 'Web none'}
                </span>
            )}
            {npu_used_for === 'review' && (
                <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[9px] border border-amber-500/25 text-amber-400 bg-amber-500/10">Review NPU</span>
            )}
            <Tooltip reasoning={reasoning} />
        </div>
    );
}

function Tooltip({ reasoning }: { reasoning: string }) {
    return (
        <div className="absolute bottom-full left-0 mb-1 w-48 p-2 bg-surface-3 border border-surface-4 rounded-md shadow-xl opacity-0 group-hover/badge:opacity-100 pointer-events-none transition-opacity z-50 text-[11px] text-text-secondary">
            {reasoning}
        </div>
    );
}
