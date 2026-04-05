import type { AgentSpaceReview } from './agentSpaceApi';

/** Classify reviews for UI routing: day-to-day workspace vs JimAI platform / self-change. */
export function inferReviewScope(review: AgentSpaceReview): 'workspace' | 'jimai' {
    const meta = review.metadata;
    const rs = String((meta as { review_scope?: string } | undefined)?.review_scope ?? '').toLowerCase();
    if (rs === 'jimai') return 'jimai';
    if (rs === 'workspace') return 'workspace';
    const obj = (review.objective || '').toLowerCase();
    if (obj.includes('self-improvement')) return 'jimai';
    if (obj.includes('run self-improvement')) return 'jimai';
    if (meta && typeof meta === 'object' && 'self_improve_prompt' in meta) return 'jimai';
    return 'workspace';
}
