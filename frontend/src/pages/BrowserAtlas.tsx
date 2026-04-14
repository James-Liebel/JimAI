import { useCallback, useEffect, useRef, useState } from 'react';
import * as agentApi from '../lib/agentSpaceApi';
import { Globe, Play, Square, RefreshCw, ChevronRight, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';

type AgentStatus = 'idle' | 'running' | 'done' | 'error';

interface StepLog {
    step?: number;
    type: string;
    thought?: string;
    action?: string;
    url?: string;
    error?: string;
    result?: string;
    reason?: string;
}

export default function BrowserAtlas() {
    const [sessionId, setSessionId] = useState('');
    const [sessionUrl, setSessionUrl] = useState('');
    const [screenshot, setScreenshot] = useState('');
    const [liveUrl, setLiveUrl] = useState('');
    const [navInput, setNavInput] = useState('');
    const [connecting, setConnecting] = useState(false);
    const [connectError, setConnectError] = useState('');
    const [mirrorActive, setMirrorActive] = useState(false);

    const [goal, setGoal] = useState('');
    const [agentStatus, setAgentStatus] = useState<AgentStatus>('idle');
    const [stepLog, setStepLog] = useState<StepLog[]>([]);
    const abortRef = useRef<AbortController | null>(null);
    const mirrorRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const logRef = useRef<HTMLDivElement>(null);

    const captureScreenshot = useCallback(async (sid = sessionId) => {
        if (!sid) return;
        try {
            const data = await agentApi.browserScreenshot(sid, false);
            if (data?.image_base64) setScreenshot(data.image_base64);
            if (data?.url) setLiveUrl(data.url);
        } catch { /* ignore */ }
    }, [sessionId]);

    // Live mirror — refresh screenshot every 800ms when connected
    useEffect(() => {
        if (!mirrorActive || !sessionId) return;
        mirrorRef.current = setInterval(() => void captureScreenshot(), 800);
        return () => { if (mirrorRef.current) clearInterval(mirrorRef.current); };
    }, [mirrorActive, sessionId, captureScreenshot]);

    // Scroll log to bottom on new entries
    useEffect(() => {
        logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
    }, [stepLog]);

    const connect = async () => {
        setConnecting(true);
        setConnectError('');
        try {
            const data = await agentApi.openAtlasSession(
                sessionUrl.trim() || 'https://www.google.com',
            );
            if (!data.success || !data.session_id) {
                setConnectError(data.error || 'Failed to open browser.');
                return;
            }
            setSessionId(data.session_id);
            setLiveUrl(data.url || '');
            setNavInput(data.url || '');
            setMirrorActive(true);
            await captureScreenshot(data.session_id);
        } catch (err) {
            setConnectError(err instanceof Error ? err.message : 'Connection failed.');
        } finally {
            setConnecting(false);
        }
    };

    const disconnect = async () => {
        setMirrorActive(false);
        abortRef.current?.abort();
        if (sessionId) {
            agentApi.closeBrowserSession(sessionId).catch(() => {});
            setSessionId('');
        }
        setScreenshot('');
        setLiveUrl('');
        setStepLog([]);
        setAgentStatus('idle');
    };

    const navigate = async () => {
        if (!sessionId || !navInput.trim()) return;
        let url = navInput.trim();
        if (!url.startsWith('http')) url = `https://${url}`;
        await agentApi.browserNavigate(sessionId, url);
        await captureScreenshot();
    };

    const runAgent = useCallback(() => {
        if (!sessionId || !goal.trim() || agentStatus === 'running') return;
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        setAgentStatus('running');
        setStepLog([]);

        // Use existing session — pass session_id via goal context
        // Agent runner opens its own session, so we stream and mirror simultaneously
        agentApi.runBrowserAgent(
            goal,
            liveUrl || 'https://www.google.com',
            { headless: false },
            (event) => {
                setStepLog((prev) => [...prev, event as StepLog]);
                if (event.screenshot) setScreenshot(event.screenshot);
                if (event.url) setLiveUrl(event.url);
            },
            () => setAgentStatus((s) => s === 'running' ? 'done' : s),
            ctrl.signal,
        );
    }, [sessionId, goal, agentStatus, liveUrl]);

    const stopAgent = () => {
        abortRef.current?.abort();
        setAgentStatus('idle');
    };

    const connected = Boolean(sessionId);

    return (
        <div className="flex h-full flex-col bg-surface-0 overflow-hidden">
            {/* Top bar */}
            <div className="flex items-center gap-2 border-b border-surface-3 bg-surface-1 px-4 py-2">
                <Globe size={16} className="shrink-0 text-accent-blue" />
                <span className="text-sm font-semibold text-text-primary mr-2">Atlas Browser</span>

                {connected ? (
                    <>
                        {/* URL bar */}
                        <form
                            className="flex flex-1 items-center gap-1 max-w-2xl"
                            onSubmit={(e) => { e.preventDefault(); void navigate(); }}
                        >
                            <input
                                className="flex-1 border border-surface-4 bg-surface-2 px-3 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                                value={navInput}
                                onChange={(e) => setNavInput(e.target.value)}
                                placeholder="https://"
                            />
                            <button
                                type="submit"
                                className="border border-surface-4 bg-surface-2 px-2 py-1 text-text-muted hover:text-text-primary"
                                title="Navigate"
                            >
                                <ChevronRight size={14} />
                            </button>
                        </form>

                        <button
                            onClick={() => void captureScreenshot()}
                            className="border border-surface-4 bg-surface-2 px-2 py-1 text-text-muted hover:text-text-primary"
                            title="Refresh screenshot"
                        >
                            <RefreshCw size={13} />
                        </button>

                        <button
                            onClick={() => void disconnect()}
                            className="ml-1 border border-accent-red/40 bg-accent-red/10 px-3 py-1 text-xs text-accent-red hover:bg-accent-red/20"
                        >
                            Disconnect
                        </button>
                    </>
                ) : (
                    <div className="flex flex-1 items-center gap-2">
                        <input
                            className="w-72 border border-surface-4 bg-surface-2 px-3 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                            placeholder="Start URL (default: google.com)"
                            value={sessionUrl}
                            onChange={(e) => setSessionUrl(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && void connect()}
                            disabled={connecting}
                        />
                        <button
                            onClick={() => void connect()}
                            disabled={connecting}
                            className="border border-accent-blue bg-accent-blue/10 px-4 py-1 text-sm text-accent-blue hover:bg-accent-blue/20 disabled:opacity-40"
                        >
                            {connecting ? 'Launching Chrome…' : 'Launch Chrome'}
                        </button>
                        {connectError && (
                            <span className="flex items-center gap-1 text-xs text-accent-red">
                                <AlertCircle size={12} /> {connectError}
                            </span>
                        )}
                    </div>
                )}
            </div>

            {/* Main area */}
            <div className="flex flex-1 overflow-hidden">
                {/* Browser view */}
                <div className="flex flex-1 flex-col overflow-hidden bg-surface-0">
                    {connected && liveUrl && (
                        <div className="border-b border-surface-3 px-4 py-1 text-xs text-text-muted truncate">
                            {liveUrl}
                        </div>
                    )}
                    <div className="flex flex-1 items-center justify-center overflow-auto">
                        {screenshot ? (
                            <img
                                src={`data:image/png;base64,${screenshot}`}
                                alt="Browser view"
                                className="max-h-full max-w-full object-contain"
                                style={{ imageRendering: 'auto' }}
                            />
                        ) : (
                            <div className="flex flex-col items-center gap-3 text-text-muted">
                                <Globe size={48} className="opacity-20" />
                                <p className="text-sm">
                                    {connecting
                                        ? 'Launching Chrome with your profile…'
                                        : 'Launch Chrome to get started. Your Google account and saved logins will be available.'}
                                </p>
                                {!connected && !connecting && (
                                    <button
                                        onClick={() => void connect()}
                                        className="mt-1 border border-accent-blue bg-accent-blue/10 px-5 py-2 text-sm text-accent-blue hover:bg-accent-blue/20"
                                    >
                                        Launch Chrome
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right panel — agent */}
                <div className="flex w-80 shrink-0 flex-col border-l border-surface-3 bg-surface-1">
                    <div className="border-b border-surface-3 px-4 py-2 text-xs font-semibold text-text-secondary uppercase tracking-wide">
                        AI Agent
                    </div>

                    {/* Goal input */}
                    <div className="border-b border-surface-3 p-3 space-y-2">
                        <textarea
                            rows={3}
                            className="w-full resize-none border border-surface-4 bg-surface-2 px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                            placeholder={connected ? 'Goal — e.g. "Search for qwen3 on GitHub and open the first result"' : 'Connect first, then give the AI a goal'}
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            disabled={!connected || agentStatus === 'running'}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runAgent();
                            }}
                        />
                        <div className="flex gap-2">
                            {agentStatus === 'running' ? (
                                <button
                                    onClick={stopAgent}
                                    className="flex flex-1 items-center justify-center gap-1.5 border border-accent-red/40 bg-accent-red/10 py-1.5 text-xs text-accent-red hover:bg-accent-red/20"
                                >
                                    <Square size={11} /> Stop
                                </button>
                            ) : (
                                <button
                                    onClick={runAgent}
                                    disabled={!connected || !goal.trim()}
                                    className="flex flex-1 items-center justify-center gap-1.5 border border-accent-blue bg-accent-blue/10 py-1.5 text-xs text-accent-blue hover:bg-accent-blue/20 disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                    <Play size={11} /> Run  <span className="text-text-muted">(Ctrl+↵)</span>
                                </button>
                            )}
                        </div>
                        {agentStatus === 'done' && (
                            <p className="text-xs text-accent-green">Agent finished.</p>
                        )}
                    </div>

                    {/* Step log */}
                    <div
                        ref={logRef}
                        className="flex-1 overflow-y-auto p-3 space-y-1.5 text-xs font-mono"
                    >
                        {stepLog.length === 0 && (
                            <p className="text-text-muted italic">
                                {connected ? 'No agent steps yet. Give a goal and click Run.' : 'Connect to Chrome first.'}
                            </p>
                        )}
                        {stepLog.map((s, i) => (
                            <div
                                key={i}
                                className={cn('border-l-2 pl-2 leading-relaxed', {
                                    'border-accent-blue text-text-secondary': s.type === 'opened',
                                    'border-surface-4 text-text-secondary': s.type === 'step',
                                    'border-accent-red text-accent-red': s.type === 'error',
                                    'border-accent-green text-accent-green': s.type === 'done',
                                    'border-accent-amber text-accent-amber': s.type === 'stopped',
                                })}
                            >
                                {s.type === 'opened' && <span>Opened: {s.url}</span>}
                                {s.type === 'step' && (
                                    <span>
                                        <span className="text-text-muted">#{s.step} [{s.action}] </span>
                                        {s.thought}
                                    </span>
                                )}
                                {s.type === 'error' && <span>✗ {s.error}</span>}
                                {s.type === 'done' && <span>✓ {s.result}</span>}
                                {s.type === 'stopped' && <span>⏹ {s.reason}</span>}
                            </div>
                        ))}
                        {agentStatus === 'running' && (
                            <div className="border-l-2 border-accent-blue pl-2 text-accent-blue animate-pulse">
                                thinking…
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
