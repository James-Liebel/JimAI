import * as agentApi from './agentSpaceApi';
import type { SelfImproveSuggestion } from './agentSpaceApi';

/** Same prompt as SelfCode “analyze app”; lives here so streaming survives route changes. */
export const ANALYZE_APP_PROMPT =
    'Analyze the jimAI codebase (FastAPI agent orchestration backend and React/Vite frontend). List concrete, high-impact improvements the maintainer could ask for in their next feedback prompt. Name specific areas or file paths when possible. Keep each item actionable in one or two sentences.';

export type SelfAnalyzeSnapshot = {
    analyzing: boolean;
    activity: string[];
    streamText: string;
    suggestions: SelfImproveSuggestion[];
    notes: string[];
    model: string;
    message: string;
    error: string;
};

const initialAnalyze: SelfAnalyzeSnapshot = {
    analyzing: false,
    activity: [],
    streamText: '',
    suggestions: [],
    notes: [],
    model: '',
    message: '',
    error: '',
};

let analyzeSnapshot: SelfAnalyzeSnapshot = { ...initialAnalyze };
const analyzeListeners = new Set<() => void>();

function emitAnalyze() {
    analyzeListeners.forEach((l) => l());
}

function patchAnalyze(p: Partial<SelfAnalyzeSnapshot>) {
    analyzeSnapshot = { ...analyzeSnapshot, ...p };
    emitAnalyze();
}

let analyzeAbort: AbortController | null = null;
let analyzeTimeout: ReturnType<typeof setTimeout> | null = null;

export function getSelfAnalyzeSnapshot(): SelfAnalyzeSnapshot {
    return analyzeSnapshot;
}

export function subscribeSelfAnalyze(onStoreChange: () => void) {
    analyzeListeners.add(onStoreChange);
    return () => {
        analyzeListeners.delete(onStoreChange);
    };
}

export function stopSelfAnalyzeSession() {
    analyzeAbort?.abort();
}

export function startSelfAnalyzeSession() {
    stopSelfAnalyzeSession();
    analyzeAbort = new AbortController();
    const ac = analyzeAbort;
    if (analyzeTimeout) clearTimeout(analyzeTimeout);
    analyzeTimeout = setTimeout(() => ac.abort(), agentApi.LLM_HTTP_TIMEOUT_MS);

    patchAnalyze({
        analyzing: true,
        activity: [],
        streamText: '',
        error: '',
        message: '',
    });

    const pushStep = (line: string) => {
        const stamp = new Date().toLocaleTimeString();
        analyzeSnapshot = {
            ...analyzeSnapshot,
            activity: [...analyzeSnapshot.activity.slice(-199), `${stamp} · ${line}`],
        };
        emitAnalyze();
    };

    const sawResult = { current: false };

    agentApi
        .suggestSelfImproveStream(
            { prompt: ANALYZE_APP_PROMPT, max_suggestions: 10 },
            {
                signal: ac.signal,
                onEvent: (ev) => {
                    if (ev.type === 'meta') {
                        patchAnalyze({ model: ev.model });
                        pushStep(`Using model ${ev.model} (focus: ${ev.focus})`);
                    } else if (ev.type === 'action') {
                        pushStep(ev.label);
                    } else if (ev.type === 'chunk' && ev.text) {
                        analyzeSnapshot = { ...analyzeSnapshot, streamText: analyzeSnapshot.streamText + ev.text };
                        emitAnalyze();
                    } else if (ev.type === 'progress') {
                        pushStep(`Streamed ~${ev.chars} characters from model…`);
                    } else if (ev.type === 'result') {
                        sawResult.current = true;
                        analyzeSnapshot = {
                            ...analyzeSnapshot,
                            suggestions: ev.suggestions || [],
                            notes: ev.autonomous_notes || [],
                            model: ev.model || analyzeSnapshot.model,
                        };
                        emitAnalyze();
                        pushStep(`Parsed response · ${ev.suggestions?.length ?? 0} suggestions`);
                    } else if (ev.type === 'stopped') {
                        const why = ev.reason || 'unknown';
                        pushStep(
                            why === 'client_disconnected'
                                ? 'Stopped (client disconnected)'
                                : `Stopped (${why})`,
                        );
                    } else if (ev.type === 'error') {
                        patchAnalyze({ error: ev.detail });
                    }
                },
            },
        )
        .then(() => {
            if (sawResult.current) {
                patchAnalyze({
                    message:
                        'Suggestions generated — copy any line into the prompt above, or use Insert on an item.',
                });
            } else if (!ac.signal.aborted) {
                patchAnalyze({
                    message:
                        'Analyzer ended without a full result — check the activity log and try again if needed.',
                });
            }
        })
        .catch((err: unknown) => {
            const aborted = typeof err === 'object' && err !== null && (err as Error).name === 'AbortError';
            if (aborted) {
                pushStep('Cancelled (request aborted)');
                patchAnalyze({ message: 'Self-analyzer stopped.', error: '' });
            } else {
                patchAnalyze({
                    error: err instanceof Error ? err.message : 'Failed to analyze the app.',
                });
            }
        })
        .finally(() => {
            if (analyzeTimeout) {
                clearTimeout(analyzeTimeout);
                analyzeTimeout = null;
            }
            analyzeAbort = null;
            patchAnalyze({ analyzing: false });
        });
}

// ── Strengthen (background; survives navigation) ─────────────────────────

const STRENGTHEN_APPLY_KEY = 'jimai.selfcode.applyStrengthen';
const STRENGTHEN_REVERT_KEY = 'jimai.selfcode.revertStrengthen';
const STRENGTHEN_ERR_KEY = 'jimai.selfcode.strengthenError';

const strengthenListeners = new Set<() => void>();

function emitStrengthen() {
    strengthenListeners.forEach((l) => l());
}

let strengthenBusy = false;
let strengthenSeq = 0;
let strengthenAbort: AbortController | null = null;

export function getStrengthenBusySnapshot() {
    return strengthenBusy;
}

export function subscribeStrengthen(onStoreChange: () => void) {
    strengthenListeners.add(onStoreChange);
    return () => {
        strengthenListeners.delete(onStoreChange);
    };
}

export function stopStrengthenSession() {
    strengthenAbort?.abort();
}

export function hasRevertStrengthenSnapshot() {
    try {
        return sessionStorage.getItem(STRENGTHEN_REVERT_KEY) != null;
    } catch {
        return false;
    }
}

export function startStrengthenSession(prompt: string, textBeforeStrengthen: string) {
    strengthenSeq += 1;
    const seq = strengthenSeq;
    stopStrengthenSession();
    try {
        sessionStorage.setItem(STRENGTHEN_REVERT_KEY, textBeforeStrengthen);
    } catch {
        /* ignore */
    }

    strengthenAbort = new AbortController();
    strengthenBusy = true;
    emitStrengthen();

    agentApi
        .strengthenSelfImprovePrompt({ prompt, signal: strengthenAbort.signal })
        .then((resp) => {
            if (seq !== strengthenSeq) return;
            try {
                sessionStorage.setItem(STRENGTHEN_APPLY_KEY, resp.strengthened_prompt);
            } catch {
                /* ignore */
            }
            emitStrengthen();
        })
        .catch((err: unknown) => {
            if (seq !== strengthenSeq) return;
            const aborted = typeof err === 'object' && err !== null && (err as Error).name === 'AbortError';
            if (!aborted) {
                try {
                    sessionStorage.setItem(
                        STRENGTHEN_ERR_KEY,
                        err instanceof Error ? err.message : 'Failed to strengthen prompt.',
                    );
                } catch {
                    /* ignore */
                }
            } else {
                try {
                    sessionStorage.removeItem(STRENGTHEN_REVERT_KEY);
                } catch {
                    /* ignore */
                }
            }
            emitStrengthen();
        })
        .finally(() => {
            if (seq !== strengthenSeq) return;
            strengthenBusy = false;
            strengthenAbort = null;
            emitStrengthen();
        });
}

export function consumePendingStrengthenPrompt(): string | null {
    try {
        const v = sessionStorage.getItem(STRENGTHEN_APPLY_KEY);
        if (v) {
            sessionStorage.removeItem(STRENGTHEN_APPLY_KEY);
            return v;
        }
    } catch {
        /* ignore */
    }
    return null;
}

export function consumePendingStrengthenError(): string | null {
    try {
        const v = sessionStorage.getItem(STRENGTHEN_ERR_KEY);
        if (v) {
            sessionStorage.removeItem(STRENGTHEN_ERR_KEY);
            return v;
        }
    } catch {
        /* ignore */
    }
    return null;
}

export function revertStrengthenSession(applyPrompt: (text: string) => void) {
    try {
        const v = sessionStorage.getItem(STRENGTHEN_REVERT_KEY);
        if (v != null) {
            sessionStorage.removeItem(STRENGTHEN_REVERT_KEY);
            applyPrompt(v);
            emitStrengthen();
        }
    } catch {
        /* ignore */
    }
}

// ── Persist prompt + run across routes (same tab) ─────────────────────────

export const STORAGE_IMPROVE_PROMPT = 'jimai.selfcode.improvePrompt';
export const STORAGE_RUN_ID = 'jimai.selfcode.runId';

export function persistImprovePrompt(text: string) {
    try {
        if (text) sessionStorage.setItem(STORAGE_IMPROVE_PROMPT, text);
        else sessionStorage.removeItem(STORAGE_IMPROVE_PROMPT);
    } catch {
        /* ignore */
    }
}

export function loadImprovePrompt(): string {
    try {
        return sessionStorage.getItem(STORAGE_IMPROVE_PROMPT) || '';
    } catch {
        return '';
    }
}

export function persistRunId(id: string) {
    try {
        if (id) sessionStorage.setItem(STORAGE_RUN_ID, id);
        else sessionStorage.removeItem(STORAGE_RUN_ID);
    } catch {
        /* ignore */
    }
}

export function loadRunId(): string {
    try {
        return sessionStorage.getItem(STORAGE_RUN_ID) || '';
    } catch {
        return '';
    }
}
