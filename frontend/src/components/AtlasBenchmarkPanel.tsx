import { useCallback, useRef, useState } from 'react';
import {
    CheckCircle2, XCircle, MinusCircle, Circle, Play, Square,
    RotateCcw, Download, ChevronDown, ChevronRight, Loader2, FlaskConical,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { ATLAS_TASK_CATEGORIES, type AtlasTask } from '../data/atlasTasks';
import { TASK_CRITERIA, type TaskCriteria } from '../data/atlasTaskCriteria';
import { fetchWithTimeout } from '../lib/api';

const BACKEND = 'http://127.0.0.1:8000/api/agent-space';

export type TaskGrade = 'pending' | 'running' | 'pass' | 'partial' | 'fail' | 'error';

export interface TaskResult {
    taskId: string;
    status: TaskGrade;
    stepsUsed: number;
    finalUrl: string;
    finalPageText: string;
    agentFinalResponse: string;
    agentSaidDone: boolean;
    gradeReason: string;
    timestamp: number;
}

interface Props {
    /** Run a single task: resolves once the agent loop finishes. */
    onRunTask: (prompt: string) => Promise<{
        url: string;
        pageText: string;
        agentSaidDone: boolean;
        stepsUsed: number;
        agentFinalResponse: string;
    }>;
    isAgentRunning: boolean;
    onStop: () => void;
}

function gradeTask(
    criteria: TaskCriteria | undefined,
    url: string,
    pageText: string,
    agentSaidDone: boolean,
    stepsUsed: number,
): { grade: Exclude<TaskGrade, 'pending' | 'running' | 'error'>; reason: string } {
    if (!criteria) return { grade: 'partial', reason: 'No criteria defined.' };

    const combined = (url + ' ' + pageText).toLowerCase();
    const maxSteps = criteria.maxSteps ?? 15;

    const urlOk = !criteria.successUrl?.length ||
        criteria.successUrl.some(u => url.toLowerCase().includes(u.toLowerCase()));

    const textOk = !criteria.successText?.length ||
        criteria.successText.some(t => combined.includes(t.toLowerCase()));

    const hitMax = stepsUsed >= maxSteps;
    const saidCannot = pageText.toLowerCase().includes('cannot') ||
        pageText.toLowerCase().includes("can't complete");

    if (urlOk && textOk && agentSaidDone) {
        return { grade: 'pass', reason: `URL ✓ · content indicator found · agent confirmed done (${stepsUsed} steps)` };
    }
    if (urlOk && textOk) {
        return { grade: 'partial', reason: `URL ✓ · content indicator found · agent did not say "done" (${stepsUsed} steps)` };
    }
    if (urlOk && agentSaidDone) {
        return { grade: 'partial', reason: `On correct site · agent done · content indicator not confirmed (${stepsUsed} steps)` };
    }
    if (saidCannot) {
        return { grade: 'fail', reason: 'Agent reported it cannot complete the task.' };
    }
    if (hitMax) {
        return { grade: 'fail', reason: `Hit max steps (${maxSteps}) without completing.` };
    }
    if (!urlOk) {
        const expected = criteria.successUrl?.join(' | ') ?? '(any)';
        return { grade: 'fail', reason: `Wrong URL — expected: ${expected} · got: ${url.slice(0, 60)}` };
    }
    return { grade: 'partial', reason: `Partial progress (${stepsUsed} steps, agent stopped without "done").` };
}

const GRADE_STYLE: Record<TaskGrade, string> = {
    pending: 'text-text-muted',
    running: 'text-accent-blue animate-pulse',
    pass: 'text-accent-green',
    partial: 'text-accent-amber',
    fail: 'text-accent-red',
    error: 'text-accent-red',
};

function GradeIcon({ grade, size = 13 }: { grade: TaskGrade; size?: number }) {
    if (grade === 'pass') return <CheckCircle2 size={size} className="text-accent-green" />;
    if (grade === 'fail' || grade === 'error') return <XCircle size={size} className="text-accent-red" />;
    if (grade === 'partial') return <MinusCircle size={size} className="text-accent-amber" />;
    if (grade === 'running') return <Loader2 size={size} className="text-accent-blue animate-spin" />;
    return <Circle size={size} className="text-text-muted opacity-40" />;
}

export default function AtlasBenchmarkPanel({ onRunTask, isAgentRunning, onStop }: Props) {
    const [results, setResults] = useState<Map<string, TaskResult>>(new Map());
    const [runningId, setRunningId] = useState<string | null>(null);
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [filter, setFilter] = useState<'all' | 'pending' | 'pass' | 'partial' | 'fail'>('all');
    const [search, setSearch] = useState('');
    const [expandedCat, setExpandedCat] = useState<string | null>(null);
    const abortRef = useRef(false);
    const allTasks = ATLAS_TASK_CATEGORIES.flatMap(c => c.tasks.map(t => ({ ...t, categoryName: c.name })));

    // Summary counts
    const pass = [...results.values()].filter(r => r.status === 'pass').length;
    const partial = [...results.values()].filter(r => r.status === 'partial').length;
    const fail = [...results.values()].filter(r => r.status === 'fail' || r.status === 'error').length;
    const total = results.size;

    const saveResult = useCallback(async (result: TaskResult) => {
        setResults(prev => new Map(prev).set(result.taskId, result));
        fetchWithTimeout(`${BACKEND}/benchmark/results`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(result),
        }, 8000).catch(() => {});
    }, []);

    const runSingleTask = useCallback(async (task: AtlasTask & { categoryName: string }) => {
        if (isAgentRunning) return;
        setRunningId(task.id);
        setResults(prev => {
            const next = new Map(prev);
            next.set(task.id, {
                taskId: task.id, status: 'running', stepsUsed: 0, finalUrl: '',
                finalPageText: '', agentFinalResponse: '', agentSaidDone: false,
                gradeReason: 'Running…', timestamp: Date.now(),
            });
            return next;
        });

        try {
            const { url, pageText, agentSaidDone, stepsUsed, agentFinalResponse } =
                await onRunTask(task.prompt);

            const criteria = TASK_CRITERIA[task.id];
            const { grade, reason } = gradeTask(criteria, url, pageText, agentSaidDone, stepsUsed);
            await saveResult({
                taskId: task.id, status: grade, stepsUsed, finalUrl: url,
                finalPageText: pageText.slice(0, 800), agentFinalResponse,
                agentSaidDone, gradeReason: reason, timestamp: Date.now(),
            });
        } catch (err) {
            await saveResult({
                taskId: task.id, status: 'error', stepsUsed: 0, finalUrl: '',
                finalPageText: '', agentFinalResponse: '',
                agentSaidDone: false,
                gradeReason: err instanceof Error ? err.message : 'Unknown error',
                timestamp: Date.now(),
            });
        } finally {
            setRunningId(null);
        }
    }, [isAgentRunning, onRunTask, saveResult]);

    const runAll = useCallback(async () => {
        abortRef.current = false;
        const pending = allTasks.filter(t => {
            const r = results.get(t.id);
            return !r || r.status === 'pending' || r.status === 'error';
        });
        for (const task of pending) {
            if (abortRef.current) break;
            await runSingleTask(task);
            await new Promise(r => setTimeout(r, 800)); // brief pause between tasks
        }
    }, [allTasks, results, runSingleTask]);

    const stopAll = useCallback(() => {
        abortRef.current = true;
        onStop();
        setRunningId(null);
    }, [onStop]);

    const reset = useCallback(() => {
        abortRef.current = true;
        setResults(new Map());
        setRunningId(null);
    }, []);

    const exportResults = useCallback(() => {
        const data = allTasks.map(t => ({
            id: t.id,
            label: t.label,
            category: (t as any).categoryName ?? '',
            prompt: t.prompt,
            criteria: TASK_CRITERIA[t.id],
            result: results.get(t.id) ?? null,
        }));
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `atlas-benchmark-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }, [allTasks, results]);

    // Filtered + searched task list
    const visibleTasks = allTasks.filter(t => {
        const r = results.get(t.id);
        const status: TaskGrade = r?.status ?? 'pending';
        if (filter !== 'all' && status !== filter) return false;
        if (search) {
            const q = search.toLowerCase();
            return t.label.toLowerCase().includes(q) ||
                (t as any).categoryName?.toLowerCase().includes(q) ||
                t.prompt.toLowerCase().includes(q);
        }
        return true;
    });

    // Group visible tasks by category for display
    const grouped = ATLAS_TASK_CATEGORIES.map(cat => ({
        name: cat.name,
        tasks: visibleTasks.filter(t => cat.tasks.some(ct => ct.id === t.id)),
    })).filter(g => g.tasks.length > 0);

    return (
        <div className="flex flex-col h-full min-h-0 bg-surface-1">
            {/* Header */}
            <div className="shrink-0 border-b border-surface-3 px-3 py-2 space-y-2">
                <div className="flex items-center gap-2">
                    <FlaskConical size={13} className="text-accent-blue shrink-0" />
                    <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wide flex-1">
                        Benchmark
                    </span>
                    <button
                        onClick={() => runAll().catch(() => {})}
                        disabled={isAgentRunning}
                        className="flex items-center gap-1 px-2 py-0.5 rounded border border-accent-green/40 bg-accent-green/10 text-accent-green text-[10px] font-medium hover:bg-accent-green/20 disabled:opacity-30 transition-colors"
                        title="Run all pending tasks"
                    >
                        <Play size={9} />
                        Run all
                    </button>
                    {isAgentRunning && (
                        <button
                            onClick={stopAll}
                            className="flex items-center gap-1 px-2 py-0.5 rounded border border-accent-red/40 bg-accent-red/10 text-accent-red text-[10px] font-medium hover:bg-accent-red/20 transition-colors"
                        >
                            <Square size={9} />
                            Stop
                        </button>
                    )}
                    <button onClick={reset} title="Reset all results" className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors">
                        <RotateCcw size={10} />
                    </button>
                    <button onClick={exportResults} title="Export results as JSON" className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors">
                        <Download size={10} />
                    </button>
                </div>

                {/* Summary bar */}
                {total > 0 && (
                    <div className="flex items-center gap-3 text-[10px]">
                        <span className="text-text-muted">{total}/100</span>
                        <span className="text-accent-green font-mono">✓{pass}</span>
                        <span className="text-accent-amber font-mono">~{partial}</span>
                        <span className="text-accent-red font-mono">✗{fail}</span>
                        <div className="flex-1 h-1 rounded-full bg-surface-3 overflow-hidden">
                            <div
                                className="h-full bg-accent-green rounded-full transition-all"
                                style={{ width: `${(pass / 100) * 100}%` }}
                            />
                        </div>
                    </div>
                )}

                {/* Filter + search */}
                <div className="flex items-center gap-1">
                    {(['all', 'pending', 'pass', 'partial', 'fail'] as const).map(f => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={cn(
                                'px-1.5 py-0.5 rounded text-[10px] capitalize transition-colors',
                                filter === f
                                    ? 'bg-accent-blue/15 text-accent-blue'
                                    : 'text-text-muted hover:bg-surface-2',
                            )}
                        >
                            {f}
                        </button>
                    ))}
                </div>
                <input
                    className="w-full border border-surface-4 bg-surface-2 rounded px-2 py-0.5 text-[11px] text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                    placeholder="Search tasks…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                />
            </div>

            {/* Task list */}
            <div className="flex-1 overflow-y-auto min-h-0">
                {grouped.map(cat => (
                    <div key={cat.name}>
                        <button
                            onClick={() => setExpandedCat(p => p === cat.name ? null : cat.name)}
                            className="w-full flex items-center justify-between px-2.5 py-1.5 bg-surface-0 border-b border-surface-3 hover:bg-surface-2 transition-colors sticky top-0 z-10"
                        >
                            <span className="text-[10px] font-semibold text-text-secondary uppercase tracking-wide">
                                {cat.name}
                            </span>
                            <span className="flex items-center gap-2">
                                <span className="text-[10px] text-text-muted">{cat.tasks.length}</span>
                                {expandedCat === cat.name
                                    ? <ChevronDown size={9} className="text-text-muted" />
                                    : <ChevronRight size={9} className="text-text-muted" />
                                }
                            </span>
                        </button>

                        {(expandedCat === cat.name || search || filter !== 'all') && cat.tasks.map(task => {
                            const result = results.get(task.id);
                            const status: TaskGrade = task.id === runningId ? 'running' : (result?.status ?? 'pending');
                            const criteria = TASK_CRITERIA[task.id];
                            const isExpanded = expandedId === task.id;

                            return (
                                <div key={task.id} className={cn('border-b border-surface-3/50', isExpanded && 'bg-surface-0')}>
                                    <div className="flex items-start gap-2 px-2.5 py-2">
                                        <div className="mt-0.5 shrink-0">
                                            <GradeIcon grade={status} />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <button
                                                onClick={() => setExpandedId(p => p === task.id ? null : task.id)}
                                                className="w-full text-left"
                                            >
                                                <span className={cn('block text-[11px] font-medium leading-snug', GRADE_STYLE[status])}>
                                                    {task.label}
                                                </span>
                                                {result && result.status !== 'pending' && result.status !== 'running' && (
                                                    <span className="block text-[10px] text-text-muted leading-tight mt-0.5 truncate">
                                                        {result.gradeReason}
                                                    </span>
                                                )}
                                                {criteria && status === 'pending' && (
                                                    <span className="block text-[10px] text-text-muted leading-tight mt-0.5 truncate">
                                                        {criteria.description}
                                                    </span>
                                                )}
                                            </button>
                                        </div>
                                        <button
                                            onClick={() => runSingleTask({ ...task, categoryName: cat.name } as any).catch(() => {})}
                                            disabled={isAgentRunning}
                                            className="shrink-0 p-1 rounded text-text-muted hover:text-accent-blue hover:bg-surface-2 disabled:opacity-30 transition-colors"
                                            title="Run this task"
                                        >
                                            {status === 'running'
                                                ? <Loader2 size={10} className="animate-spin text-accent-blue" />
                                                : <Play size={10} />
                                            }
                                        </button>
                                    </div>

                                    {/* Expanded detail */}
                                    {isExpanded && (
                                        <div className="px-7 pb-3 space-y-2">
                                            <div className="rounded border border-surface-4 bg-surface-2 p-2 space-y-1.5">
                                                <p className="text-[10px] font-medium text-text-muted uppercase tracking-wide">Completion criteria</p>
                                                <p className="text-[11px] text-text-secondary">{criteria?.description ?? 'No criteria defined.'}</p>
                                                {criteria?.successUrl && (
                                                    <p className="text-[10px] text-text-muted font-mono">URL: {criteria.successUrl.join(' | ')}</p>
                                                )}
                                                {criteria?.successText && (
                                                    <p className="text-[10px] text-text-muted font-mono">Text: {criteria.successText.slice(0, 4).join(', ')}</p>
                                                )}
                                                <p className="text-[10px] text-text-muted">Max steps: {criteria?.maxSteps ?? 15}</p>
                                            </div>

                                            {result && result.status !== 'pending' && (
                                                <div className="rounded border border-surface-4 bg-surface-2 p-2 space-y-1.5">
                                                    <p className="text-[10px] font-medium text-text-muted uppercase tracking-wide">Result</p>
                                                    <p className={cn('text-[11px] font-medium', GRADE_STYLE[result.status])}>
                                                        {result.status.toUpperCase()} — {result.gradeReason}
                                                    </p>
                                                    <p className="text-[10px] text-text-muted font-mono break-all">URL: {result.finalUrl.slice(0, 80)}</p>
                                                    <p className="text-[10px] text-text-muted">Steps: {result.stepsUsed} · Done: {result.agentSaidDone ? 'yes' : 'no'}</p>
                                                    {result.agentFinalResponse && (
                                                        <p className="text-[10px] text-text-secondary italic">"{result.agentFinalResponse.slice(0, 120)}"</p>
                                                    )}
                                                </div>
                                            )}

                                            <div className="rounded border border-surface-4 bg-surface-0 p-2">
                                                <p className="text-[10px] font-medium text-text-muted uppercase tracking-wide mb-1">Task prompt</p>
                                                <p className="text-[10px] text-text-secondary leading-relaxed">{task.prompt}</p>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                ))}

                {visibleTasks.length === 0 && (
                    <div className="flex items-center justify-center py-12 text-[11px] text-text-muted">
                        No tasks match the current filter.
                    </div>
                )}
            </div>
        </div>
    );
}
