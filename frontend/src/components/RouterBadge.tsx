import { useState } from 'react';
import { Info } from 'lucide-react';
import type { RoutingDecision } from '../lib/types';
import { cn } from '../lib/utils';

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
    deep: 'bg-status-warning/15 text-status-warning border-status-warning/25',
};

function modelShortName(model: string): string {
    if (model.includes('deepseek-r1')) return 'R1-14B';
    if (model.includes('qwen2.5-coder:32b')) return 'Coder-32B';
    if (model.includes('qwen2.5-coder:14b')) return 'Coder-14B';
    if (model.includes('qwen2.5-coder:7b')) return 'Coder-7B';
    if (model.includes('qwen2.5-coder:3b')) return 'Coder-3B';
    if (model.includes('qwen3:32b')) return 'Qwen3-32B';
    if (model.includes('qwen3:14b')) return 'Qwen3-14B';
    if (model.includes('qwen3:8b')) return 'Qwen3-8B';
    if (model.includes('qwen2.5vl')) return 'VL-7B';
    if (model.includes('qwen2-math')) return 'Math-7B';
    if (model.includes('qwen2.5:32b')) return 'Qwen2.5-32B';
    if (model.includes('nomic-embed')) return 'Embed';
    return model.split(':')[0];
}

const SPEED_STYLES: Record<string, string> = {
    turbo: 'bg-accent-green/15 text-accent-green border-accent-green/30',
    fast: 'bg-accent-blue/10 text-accent-blue border-accent-blue/25',
    balanced: 'bg-surface-4/40 text-text-secondary border-surface-4',
    deep: 'bg-status-warning/15 text-status-warning border-status-warning/30',
};

const SPEED_LABEL: Record<string, string> = {
    turbo: '⚡ turbo',
    fast: '⚡ fast',
    balanced: 'balanced',
    deep: '◆ deep',
};

function SpeedChip({ speedMode }: { speedMode: string | undefined }) {
    if (!speedMode) return null;
    const style = SPEED_STYLES[speedMode] || SPEED_STYLES.balanced;
    const label = SPEED_LABEL[speedMode] || speedMode;
    return (
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded-badge text-[9px] uppercase tracking-wide border ${style}`}>
            {label}
        </span>
    );
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

    if (compare_models && compare_models.length >= 2 && judge_model) {
        return (
            <div className="flex items-center gap-1 group/badge relative flex-wrap">
                <span className="text-[10px] text-text-muted">Compare:</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-badge text-[10px] border ${ROLE_STYLES.chat}`}>
                    {modelShortName(compare_models[0])}
                </span>
                <span className="text-[9px] text-text-muted">vs</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-badge text-[10px] border ${ROLE_STYLES.chat}`}>
                    {modelShortName(compare_models[1])}{npu_used_for === 'model_b' && <span className="ml-0.5 text-[9px] text-status-warning">NPU</span>}
                </span>
                <span className="text-[9px] text-text-muted">→</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-badge text-[10px] border ${ROLE_STYLES.chat}`}>
                    {modelShortName(judge_model)}
                </span>
                <SpeedChip speedMode={speed_mode} />
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
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded-badge text-[10px] border ${ROLE_STYLES[r] || ROLE_STYLES.chat}`}>
                                {modelShortName(model)}
                            </span>
                        </span>
                    );
                })}
                <SpeedChip speedMode={speed_mode} />
                <Tooltip reasoning={reasoning} />
            </div>
        );
    }

    return (
        <div className="group/badge relative inline-flex items-center gap-1.5">
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-badge text-[10px] border ${ROLE_STYLES[role] || ROLE_STYLES.chat}`}>
                {manual_override && (
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor" className="opacity-60">
                        <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/>
                    </svg>
                )}
                {modelShortName(primary_model)}
            </span>
            <SpeedChip speedMode={speed_mode} />
            {auto_web_research_attempted && (
                <span
                    className={`inline-flex items-center px-1.5 py-0.5 rounded-badge text-[9px] border ${
                        auto_web_research_ok
                            ? 'border-accent-green/30 text-accent-green bg-accent-green/10'
                            : auto_web_research_offline
                                ? 'border-accent-red/30 text-accent-red bg-accent-red/10'
                                : 'border-status-warning/30 text-status-warning bg-status-warning/10'
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
                <span className="inline-flex items-center px-1.5 py-0.5 rounded-badge text-[9px] border border-status-warning/25 text-status-warning bg-status-warning/10">Review NPU</span>
            )}
            <Tooltip reasoning={reasoning} />
        </div>
    );
}

function Tooltip({ reasoning }: { reasoning: string }) {
    // Hover never fires on phones/tablets, so touch devices get an explicit ⓘ
    // toggle instead of the hover reveal (same detection idiom as CodeBlock).
    const [open, setOpen] = useState(false);
    const isTouchDevice = 'ontouchstart' in window;
    if (!reasoning) return null;
    return (
        <>
            {isTouchDevice && (
                <button
                    type="button"
                    onClick={() => setOpen((v) => !v)}
                    aria-label="Routing reasoning"
                    aria-expanded={open}
                    className={cn('-m-1 rounded p-2', open ? 'text-text-secondary' : 'text-text-muted')}
                >
                    <Info size={13} />
                </button>
            )}
            <div className={cn(
                'absolute bottom-full left-0 mb-1 w-48 p-2 bg-surface-3 border border-surface-4 rounded-card shadow-elevation-2 transition-opacity z-50 text-[11px] text-text-secondary',
                open ? 'opacity-100' : 'opacity-0 pointer-events-none group-hover/badge:opacity-100',
            )}>
                {reasoning}
            </div>
        </>
    );
}
