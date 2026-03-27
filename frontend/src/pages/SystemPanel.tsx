import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Cpu, ExternalLink, FolderOpen, Monitor, Play, Search, Terminal, XCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { queueChatPrompt } from '../lib/chatBridge';
import { cn } from '../lib/utils';
import type { SystemAgentEvent, SystemAgentMode, SystemAgentPlanStep, SystemAgentStats, SystemFileInfo, SystemProcessInfo } from '../lib/systemAgentApi';
import { browseSystemFilesystem, confirmSystemAgent, getSystemAgentStats, killSystemProcess, listSystemAgentProcesses, openSystemPath, readSystemFile, streamSystemAgent, takeSystemScreenshot } from '../lib/systemAgentApi';

type StepStatus = 'pending' | 'running' | 'success' | 'skipped' | 'error';
type StepState = { status: StepStatus; result?: any; error?: string };
type LogEntry = { id: string; tone: 'default' | 'good' | 'warn' | 'bad'; text: string };
type PendingModal = { kind: 'agent'; sessionId: string; description: string; risk: 'caution' | 'destructive'; step: number } | { kind: 'kill'; pid: number; processName: string };

function sessionId() {
    try {
        if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    } catch {}
    return `system-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function isTextFile(file: SystemFileInfo | null) {
    if (!file || file.is_dir) return false;
    return ['.bat', '.c', '.cfg', '.cpp', '.cs', '.css', '.csv', '.env', '.go', '.h', '.html', '.ini', '.java', '.js', '.json', '.jsx', '.kt', '.md', '.php', '.ps1', '.py', '.rb', '.rs', '.scss', '.sh', '.sql', '.toml', '.ts', '.tsx', '.txt', '.xml', '.yaml', '.yml'].includes(file.extension.toLowerCase());
}

function toneClass(tone: LogEntry['tone']) {
    if (tone === 'good') return 'border-accent-green/30 bg-accent-green/10 text-accent-green';
    if (tone === 'warn') return 'border-accent-amber/30 bg-accent-amber/10 text-accent-amber';
    if (tone === 'bad') return 'border-accent-red/30 bg-accent-red/10 text-accent-red';
    return 'border-surface-3 bg-surface-0 text-text-secondary';
}

function percentWidth(value: number) {
    const safe = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
    return `${safe}%`;
}

function resultText(result: any) {
    if (!result) return 'No result';
    if (typeof result.analysis === 'string') return result.analysis;
    if (typeof result.content === 'string') return result.content.split('\n').slice(0, 20).join('\n');
    if (typeof result.stdout === 'string' || typeof result.stderr === 'string') return [result.stdout, result.stderr].filter(Boolean).join('\n').trim();
    return JSON.stringify(result, null, 2);
}

export default function SystemPanel() {
    const navigate = useNavigate();
    const [task, setTask] = useState('Find all Python files over 500 lines in my Documents folder and summarize each one.');
    const [mode, setMode] = useState<SystemAgentMode>('supervised');
    const [activeSessionId, setActiveSessionId] = useState(sessionId());
    const [running, setRunning] = useState(false);
    const [plan, setPlan] = useState<SystemAgentPlanStep[]>([]);
    const [stepStates, setStepStates] = useState<Record<number, StepState>>({});
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [error, setError] = useState('');
    const [stats, setStats] = useState<SystemAgentStats | null>(null);
    const [processes, setProcesses] = useState<SystemProcessInfo[]>([]);
    const [pendingModal, setPendingModal] = useState<PendingModal | null>(null);
    const [browserOpen, setBrowserOpen] = useState(false);
    const [browserPath, setBrowserPath] = useState('~');
    const [browserItems, setBrowserItems] = useState<SystemFileInfo[]>([]);
    const [browserLoading, setBrowserLoading] = useState(false);
    const [previewFile, setPreviewFile] = useState<SystemFileInfo | null>(null);
    const [previewContent, setPreviewContent] = useState('');
    const [previewTruncated, setPreviewTruncated] = useState(false);
    const [lastScreenshot, setLastScreenshot] = useState<{ base64?: string; timestamp?: string } | null>(null);

    const appendLog = useCallback((text: string, tone: LogEntry['tone'] = 'default') => {
        setLogs((current) => [...current, { id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, tone, text }]);
    }, []);

    const loadDashboard = useCallback(async () => {
        try {
            const [statsData, processData] = await Promise.all([getSystemAgentStats(), listSystemAgentProcesses()]);
            setStats(statsData);
            setProcesses(processData.slice(0, 10));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load system data');
        }
    }, []);

    useEffect(() => {
        loadDashboard().catch(() => {});
        const id = window.setInterval(() => loadDashboard().catch(() => {}), 5000);
        return () => window.clearInterval(id);
    }, [loadDashboard]);

    const openBrowserAt = useCallback(async (path: string) => {
        setBrowserLoading(true);
        try {
            const data = await browseSystemFilesystem(path);
            setBrowserPath(data.path);
            setBrowserItems(data.items);
            setPreviewFile(null);
            setPreviewContent('');
            setPreviewTruncated(false);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Browse failed');
        } finally {
            setBrowserLoading(false);
        }
    }, []);

    const onEvent = useCallback((event: SystemAgentEvent, currentSessionId: string) => {
        if (event.type === 'plan') {
            const steps = (event.data.steps || []) as SystemAgentPlanStep[];
            setPlan(steps);
            setStepStates(steps.reduce<Record<number, StepState>>((acc, step) => ({ ...acc, [step.step]: { status: 'pending' } }), {}));
            appendLog(`Plan ready with ${steps.length} steps.`, 'good');
            return;
        }
        if (event.type === 'step_start') {
            setStepStates((current) => ({ ...current, [Number(event.data.step)]: { status: 'running' } }));
            return;
        }
        if (event.type === 'step_result') {
            const step = Number(event.data.step);
            const skipped = Boolean(event.data.skipped);
            setStepStates((current) => ({ ...current, [step]: { status: skipped ? 'skipped' : event.data.success ? 'success' : 'error', result: event.data.result, error: event.data.reason } }));
            if (event.data.reason) appendLog(`Step ${step}: ${event.data.reason}`, skipped ? 'warn' : 'bad');
            return;
        }
        if (event.type === 'step_error') {
            const step = Number(event.data.step);
            setStepStates((current) => ({ ...current, [step]: { status: 'error', error: String(event.data.error || 'Unknown error') } }));
            appendLog(`Step ${step} failed: ${String(event.data.error || 'Unknown error')}`, 'bad');
            return;
        }
        if (event.type === 'confirmation_needed') {
            setPendingModal({ kind: 'agent', sessionId: currentSessionId, description: String(event.data.description || ''), risk: (event.data.risk as 'caution' | 'destructive') || 'caution', step: Number(event.data.step || 0) });
            return;
        }
        if (event.type === 'text') {
            const text = String(event.data.text || '').trim();
            if (text) appendLog(text);
            return;
        }
        if (event.type === 'complete') {
            setRunning(false);
            appendLog(`Task complete: ${Number(event.data.steps_executed || 0)} of ${Number(event.data.steps_planned || 0)} steps executed.`, event.data.success ? 'good' : 'warn');
        }
    }, [appendLog]);

    const handleRun = useCallback(async () => {
        if (!task.trim() || running) return;
        const currentSessionId = sessionId();
        setActiveSessionId(currentSessionId);
        setRunning(true);
        setPlan([]);
        setStepStates({});
        setLogs([]);
        setError('');
        setPendingModal(null);
        try {
            await streamSystemAgent(task.trim(), currentSessionId, mode, (event) => onEvent(event, currentSessionId));
        } catch (err) {
            setRunning(false);
            setError(err instanceof Error ? err.message : 'System agent run failed');
            appendLog(err instanceof Error ? err.message : 'System agent run failed', 'bad');
        }
    }, [appendLog, mode, onEvent, running, task]);

    const confirmModal = useCallback(async (approved: boolean) => {
        if (!pendingModal) return;
        try {
            if (pendingModal.kind === 'agent') {
                await confirmSystemAgent(pendingModal.sessionId, approved);
                appendLog(`${approved ? 'Approved' : 'Denied'} step ${pendingModal.step}.`, approved ? 'good' : 'warn');
            } else if (approved) {
                const result = await killSystemProcess(pendingModal.pid);
                appendLog(result.killed ? `Killed ${pendingModal.processName}.` : `Could not kill ${pendingModal.processName}: ${result.reason || 'unknown error'}`, result.killed ? 'good' : 'bad');
                await loadDashboard();
            } else {
                appendLog(`Cancelled kill request for ${pendingModal.processName}.`, 'warn');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Confirmation failed');
        } finally {
            setPendingModal(null);
        }
    }, [appendLog, loadDashboard, pendingModal]);

    const handleScreenshot = useCallback(async () => {
        try {
            const shot = await takeSystemScreenshot(1);
            setLastScreenshot({ base64: shot.base64, timestamp: shot.timestamp });
            appendLog(`Captured screenshot at ${shot.timestamp}.`, 'good');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Screenshot failed');
        }
    }, [appendLog]);

    const handleFileSelect = useCallback(async (file: SystemFileInfo) => {
        if (file.is_dir) {
            await openBrowserAt(file.path);
            return;
        }
        setPreviewFile(file);
        if (!isTextFile(file)) {
            setPreviewContent('Binary or non-previewable file. Use Open to launch it.');
            setPreviewTruncated(false);
            return;
        }
        try {
            const data = await readSystemFile(file.path, 12000);
            setPreviewContent(data.content);
            setPreviewTruncated(data.truncated);
        } catch (err) {
            setPreviewContent(err instanceof Error ? err.message : 'Preview failed');
            setPreviewTruncated(false);
        }
    }, [openBrowserAt]);

    const directories = useMemo(() => browserItems.filter((item) => item.is_dir), [browserItems]);

    return (
        <div className="h-full overflow-auto p-4 md:p-6">
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.9fr)_360px]">
                <div className="space-y-4">
                    <section className="rounded-card border border-surface-3 bg-surface-1 p-4 space-y-4">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <h1 className="text-lg font-semibold text-text-primary">System Panel</h1>
                                <p className="mt-1 text-xs text-text-secondary">Local system access with plan-first execution, confirmations, and live results.</p>
                            </div>
                            <div className="rounded-full border border-surface-3 bg-surface-0 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-text-secondary">Session {activeSessionId.slice(0, 8)}</div>
                        </div>
                        <textarea value={task} onChange={(event) => setTask(event.target.value)} rows={6} className="w-full rounded-card border border-surface-3 bg-surface-0 px-3 py-3 text-sm" />
                        <div className="flex flex-wrap gap-2">
                            <button type="button" onClick={() => setMode('supervised')} className={cn('rounded-btn border px-3 py-2 text-left', mode === 'supervised' ? 'border-accent-blue/40 bg-accent-blue/10' : 'border-surface-3 bg-surface-0')}><p className="text-sm text-text-primary">Supervised</p><p className="mt-1 text-[11px] text-text-secondary">Confirm caution and destructive steps.</p></button>
                            <button type="button" onClick={() => setMode('autonomous')} className={cn('rounded-btn border px-3 py-2 text-left', mode === 'autonomous' ? 'border-accent-blue/40 bg-accent-blue/10' : 'border-surface-3 bg-surface-0')}><p className="text-sm text-text-primary">Autonomous</p><p className="mt-1 text-[11px] text-text-secondary">Only destructive steps require confirmation.</p></button>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <button type="button" onClick={() => void handleRun()} disabled={running} className="inline-flex items-center gap-2 rounded-btn border border-accent-green/40 bg-accent-green/10 px-4 py-2 text-sm text-accent-green disabled:opacity-60"><Play size={16} />{running ? 'Running Agent...' : 'Run Agent'}</button>
                            <button type="button" onClick={() => { setBrowserOpen(true); void openBrowserAt(browserPath || '~'); }} className="inline-flex items-center gap-2 rounded-btn border border-surface-3 bg-surface-0 px-3 py-2 text-xs text-text-primary"><FolderOpen size={14} />Browse Files</button>
                            <button type="button" onClick={() => void loadDashboard()} className="inline-flex items-center gap-2 rounded-btn border border-surface-3 bg-surface-0 px-3 py-2 text-xs text-text-primary"><Activity size={14} />System Stats</button>
                            <button type="button" onClick={() => setTask('Find Python files in my Documents folder and summarize the important ones.')} className="inline-flex items-center gap-2 rounded-btn border border-surface-3 bg-surface-0 px-3 py-2 text-xs text-text-primary"><Search size={14} />Search Files</button>
                            <button type="button" onClick={() => void handleScreenshot()} className="inline-flex items-center gap-2 rounded-btn border border-surface-3 bg-surface-0 px-3 py-2 text-xs text-text-primary"><Monitor size={14} />Screenshot</button>
                        </div>
                    </section>

                    <section className="rounded-card border border-surface-3 bg-surface-1 p-4 space-y-3">
                        <h2 className="text-sm font-semibold text-text-primary">Agent Activity Feed</h2>
                        {plan.length === 0 && <div className="rounded-btn border border-surface-3 bg-surface-0 p-4 text-sm text-text-secondary">Submit a task to generate a plan and stream execution here.</div>}
                        {plan.map((step) => {
                            const state = stepStates[step.step] || { status: 'pending' as StepStatus };
                            const badge = state.status === 'success' ? 'border-accent-green/30 bg-accent-green/10 text-accent-green' : state.status === 'running' ? 'border-accent-blue/30 bg-accent-blue/10 text-accent-blue' : state.status === 'error' ? 'border-accent-red/30 bg-accent-red/10 text-accent-red' : state.status === 'skipped' ? 'border-accent-amber/30 bg-accent-amber/10 text-accent-amber' : 'border-surface-3 bg-surface-0 text-text-secondary';
                            const card = step.is_destructive && state.status === 'pending' ? 'border-accent-amber/30 bg-accent-amber/10' : 'border-surface-3 bg-surface-0';
                            return (
                                <div key={step.step} className={cn('rounded-btn border p-3', card)}>
                                    <div className="flex items-start justify-between gap-3">
                                        <div><p className="text-sm text-text-primary">{step.step}. {step.description}</p><p className="mt-1 text-[11px] uppercase tracking-wide text-text-secondary">{step.tool}</p></div>
                                        <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[10px] uppercase tracking-wide', badge)}>{state.status === 'success' ? <CheckCircle2 size={14} /> : state.status === 'error' ? <XCircle size={14} /> : state.status === 'running' ? <Activity size={14} /> : <AlertTriangle size={14} />}{state.status}</span>
                                    </div>
                                    {(state.result || state.error) && <details className="mt-3" open={state.status === 'error'}><summary className="cursor-pointer text-xs text-text-secondary">View result</summary><pre className="mt-2 whitespace-pre-wrap p-3 text-[11px] text-text-primary">{state.error || resultText(state.result)}</pre></details>}
                                </div>
                            );
                        })}
                        {lastScreenshot?.base64 && <div className="rounded-btn border border-surface-3 bg-surface-0 p-3"><div className="flex items-center justify-between gap-2"><p className="text-sm text-text-primary">Latest Screenshot</p><span className="text-[11px] text-text-secondary">{lastScreenshot.timestamp}</span></div><img src={`data:image/png;base64,${lastScreenshot.base64}`} alt="Latest system screenshot" className="mt-3 max-h-[280px] w-full rounded-btn border border-surface-3 object-contain" /></div>}
                        <div className="space-y-2">{logs.length === 0 ? <p className="text-xs text-text-secondary">No agent commentary yet.</p> : logs.map((entry) => <div key={entry.id} className={cn('rounded-btn border px-3 py-2 text-sm whitespace-pre-wrap', toneClass(entry.tone))}>{entry.text}</div>)}</div>
                        {error && <div className="rounded-btn border border-accent-red/30 bg-accent-red/10 px-3 py-2 text-sm text-accent-red">{error}</div>}
                    </section>
                </div>

                <aside className="space-y-4">
                    <section className="rounded-card border border-surface-3 bg-surface-1 p-4 space-y-3">
                        <div className="flex items-center gap-2"><Cpu size={16} className="text-accent-blue" /><h2 className="text-sm font-semibold text-text-primary">System Dashboard</h2></div>
                        <Metric label="CPU" value={`${stats?.cpu_percent ?? 0}%`} percent={stats?.cpu_percent ?? 0} detail={`${stats?.cpu_cores ?? 0} cores`} />
                        <Metric label="RAM" value={`${stats?.memory_used_gb ?? 0}/${stats?.memory_total_gb ?? 0} GB`} percent={stats?.memory_percent ?? 0} detail={`${stats?.memory_percent ?? 0}% used`} />
                        <Metric label="Disk" value={`${stats?.disk_used_gb ?? 0}/${stats?.disk_total_gb ?? 0} GB`} percent={stats?.disk_percent ?? 0} detail={`${stats?.disk_percent ?? 0}% used`} />
                        <Metric label={stats?.gpu?.name || 'GPU'} value={`${stats?.gpu?.memory_used_mb ?? 0}/${stats?.gpu?.memory_total_mb ?? 0} MB`} percent={stats?.gpu?.utilization_percent ?? 0} detail={stats?.gpu?.temperature_c ? `${stats.gpu.temperature_c}°C` : 'No GPU stats'} />
                    </section>
                    <section className="rounded-card border border-surface-3 bg-surface-1 p-4 space-y-3">
                        <div className="flex items-center gap-2"><Terminal size={16} className="text-accent-amber" /><h2 className="text-sm font-semibold text-text-primary">Top Processes</h2></div>
                        {processes.length === 0 ? <p className="text-xs text-text-secondary">No process data available.</p> : processes.map((proc) => (
                            <div key={proc.pid} className="rounded-btn border border-surface-3 bg-surface-0 p-3">
                                <div className="flex items-start justify-between gap-2">
                                    <div className="min-w-0"><p className="truncate text-sm text-text-primary">{proc.name || 'Unknown process'}</p><p className="mt-1 text-[11px] text-text-secondary">PID {proc.pid} • {proc.memory_mb} MB • CPU {proc.cpu_percent}%</p></div>
                                    <button type="button" onClick={() => setPendingModal({ kind: 'kill', pid: proc.pid, processName: proc.name })} className="rounded-btn border border-accent-red/30 px-2 py-1 text-[11px] text-accent-red">Kill</button>
                                </div>
                            </div>
                        ))}
                    </section>
                </aside>
            </div>

            {browserOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
                    <div className="max-h-[90vh] w-full max-w-6xl overflow-hidden rounded-card border border-surface-3 bg-surface-1 shadow-2xl">
                        <div className="flex items-center justify-between border-b border-surface-3 px-4 py-3"><div><p className="text-sm font-semibold text-text-primary">File Browser</p><p className="text-[11px] text-text-secondary">{browserPath}</p></div><div className="flex gap-2"><button type="button" onClick={() => { const next = browserPath.replace(/[\\/][^\\/]+$/, ''); if (next && next !== browserPath) void openBrowserAt(next); }} className="rounded-btn border border-surface-3 px-3 py-2 text-xs text-text-secondary">Up</button><button type="button" onClick={() => setBrowserOpen(false)} className="rounded-btn border border-surface-3 px-3 py-2 text-xs text-text-secondary">Close</button></div></div>
                        <div className="grid max-h-[calc(90vh-65px)] md:grid-cols-[220px_minmax(0,1fr)_360px]">
                            <div className="border-r border-surface-3 bg-surface-0 p-3 overflow-auto"><p className="mb-2 text-[11px] uppercase tracking-wide text-text-secondary">Directories</p>{browserLoading ? <p className="text-xs text-text-secondary">Loading...</p> : directories.map((item) => <button key={item.path} type="button" onClick={() => void openBrowserAt(item.path)} className="mb-2 block w-full rounded-btn border border-surface-3 px-3 py-2 text-left text-sm text-text-primary hover:bg-surface-1">{item.name}</button>)}</div>
                            <div className="border-r border-surface-3 p-3 overflow-auto"><p className="mb-2 text-[11px] uppercase tracking-wide text-text-secondary">Items</p>{browserItems.map((item) => <button key={item.path} type="button" onClick={() => void handleFileSelect(item)} className="mb-2 flex w-full items-center justify-between rounded-btn border border-surface-3 bg-surface-0 px-3 py-2 text-left hover:bg-surface-1"><span className="min-w-0 truncate text-sm text-text-primary">{item.is_dir ? `${item.name}\\` : item.name}</span><span className="ml-3 flex-shrink-0 text-[11px] text-text-secondary">{item.size_human}</span></button>)}</div>
                            <div className="p-3 overflow-auto"><p className="mb-2 text-[11px] uppercase tracking-wide text-text-secondary">Preview</p>{!previewFile ? <p className="text-sm text-text-secondary">Select a file to preview it.</p> : <div className="space-y-3"><div><p className="text-sm font-semibold text-text-primary">{previewFile.name}</p><p className="mt-1 text-[11px] text-text-secondary">{previewFile.path}</p></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void openSystemPath(previewFile.path)} className="inline-flex items-center gap-1 rounded-btn border border-surface-3 px-3 py-2 text-xs text-text-primary"><ExternalLink size={14} />Open</button><button type="button" onClick={() => { if (navigator.clipboard) void navigator.clipboard.writeText(previewFile.path); }} className="rounded-btn border border-surface-3 px-3 py-2 text-xs text-text-primary">Copy Path</button><button type="button" onClick={() => { queueChatPrompt(`Analyze this file:\n${previewFile.path}`); navigate('/chat'); }} className="rounded-btn border border-accent-blue/30 px-3 py-2 text-xs text-accent-blue">Ask AI About This File</button></div><pre className="whitespace-pre-wrap p-3 text-[11px] text-text-primary">{previewContent}</pre>{previewTruncated && <p className="text-[11px] text-text-secondary">Preview truncated for readability.</p>}<div className="rounded-btn border border-surface-3 bg-surface-0 p-3 text-[11px] text-text-secondary">{previewFile.size_human} • modified {previewFile.modified}</div></div>}</div>
                        </div>
                    </div>
                </div>
            )}

            {pendingModal && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4">
                    <div className="w-full max-w-md rounded-card border border-surface-3 bg-surface-1 p-5">
                        <div className="flex items-start gap-3">
                            {pendingModal.kind === 'agent' && pendingModal.risk === 'destructive' ? <AlertTriangle className="mt-0.5 text-accent-red" size={18} /> : pendingModal.kind === 'kill' ? <XCircle className="mt-0.5 text-accent-red" size={18} /> : <AlertTriangle className="mt-0.5 text-accent-amber" size={18} />}
                            <div className="flex-1"><p className="text-sm font-semibold text-text-primary">{pendingModal.kind === 'agent' ? 'Confirmation Needed' : 'Kill Process?'}</p><p className="mt-2 text-sm text-text-secondary">{pendingModal.kind === 'agent' ? pendingModal.description : `Terminate ${pendingModal.processName} (PID ${pendingModal.pid})?`}</p>{pendingModal.kind === 'agent' && <span className={cn('mt-3 inline-flex rounded-full border px-2 py-1 text-[10px] uppercase tracking-wide', pendingModal.risk === 'destructive' ? 'border-accent-red/30 bg-accent-red/10 text-accent-red' : 'border-accent-amber/30 bg-accent-amber/10 text-accent-amber')}>{pendingModal.risk}</span>}</div>
                        </div>
                        <div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => void confirmModal(false)} className="rounded-btn border border-surface-3 px-4 py-2 text-sm text-text-secondary">Deny</button><button type="button" onClick={() => void confirmModal(true)} className="rounded-btn border border-accent-green/40 bg-accent-green/10 px-4 py-2 text-sm text-accent-green">Approve</button></div>
                    </div>
                </div>
            )}
        </div>
    );
}

function Metric({ label, value, percent, detail }: { label: string; value: string; percent: number; detail: string }) {
    return (
        <div className="rounded-btn border border-surface-3 bg-surface-0 p-3">
            <div className="flex items-center justify-between gap-3"><p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p><p className="text-sm text-text-primary">{value}</p></div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3"><div className="h-full rounded-full bg-gradient-to-r from-accent-blue to-accent-green" style={{ width: percentWidth(percent) }} /></div>
            <p className="mt-2 text-[11px] text-text-secondary">{detail}</p>
        </div>
    );
}
