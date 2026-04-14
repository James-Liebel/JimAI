import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import * as agentApi from '../lib/agentSpaceApi';
import { PageHeader } from '../components/PageHeader';
import { Camera, ChevronDown, ChevronRight, Square, Play } from 'lucide-react';

export default function AgentBrowser() {
    const [sessions, setSessions] = useState<agentApi.BrowserSessionSummary[]>([]);
    const [sessionId, setSessionId] = useState('');
    const [url, setUrl] = useState('https://example.com');
    const [selector, setSelector] = useState('body');
    const [typeText, setTypeText] = useState('');
    const [extractText, setExtractText] = useState('');
    const [screenshotBase64, setScreenshotBase64] = useState('');
    const [pageState, setPageState] = useState<agentApi.BrowserPageState | null>(null);
    const [links, setLinks] = useState<agentApi.BrowserLinkInfo[]>([]);
    const [interactiveFields, setInteractiveFields] = useState<agentApi.BrowserInteractiveField[]>([]);
    const [cursorX, setCursorX] = useState(0);
    const [cursorY, setCursorY] = useState(0);
    const [scrollStep, setScrollStep] = useState(600);
    const [imageClickMode, setImageClickMode] = useState<'click' | 'move'>('click');
    const [headedMode, setHeadedMode] = useState(false);
    const [liveMirror, setLiveMirror] = useState(false);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [quickUrl, setQuickUrl] = useState('https://');
    const [quickScreenshot, setQuickScreenshot] = useState('');
    const [quickLoading, setQuickLoading] = useState(false);
    const [quickError, setQuickError] = useState('');
    const [mirrorMs, setMirrorMs] = useState(900);
    const [selectValue, setSelectValue] = useState('');
    const [selectLabel, setSelectLabel] = useState('');
    const [pressKey, setPressKey] = useState('Tab');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    // ── AI Agent state ──────────────────────────────────────────────────
    const [agentGoal, setAgentGoal] = useState('');
    const [agentUrl, setAgentUrl] = useState('https://');
    const [agentHeadless, setAgentHeadless] = useState(false);
    const [agentRunning, setAgentRunning] = useState(false);
    const [agentSteps, setAgentSteps] = useState<agentApi.BrowserAgentStep[]>([]);
    const [agentScreenshot, setAgentScreenshot] = useState('');
    const [agentCurrentUrl, setAgentCurrentUrl] = useState('');
    const agentAbortRef = useRef<AbortController | null>(null);
    const agentLogRef = useRef<HTMLDivElement>(null);

    const refreshSessions = async () => {
        const rows = await agentApi.listBrowserSessions();
        setSessions(rows);
        if (!sessionId && rows.length > 0) setSessionId(rows[0].session_id);
    };

    const syncState = async (withLinks = true) => {
        if (!sessionId) {
            setPageState(null);
            setLinks([]);
            return;
        }
        const data = await agentApi.getBrowserState(sessionId, withLinks, 60);
        if (!data.success) {
            throw new Error((data as any).error || 'state fetch failed');
        }
        setPageState(data);
        if (data.cursor) {
            setCursorX(Math.round(data.cursor.x || 0));
            setCursorY(Math.round(data.cursor.y || 0));
        }
        setLinks(Array.isArray(data.links) ? data.links : []);
    };

    const capture = async () => {
        if (!sessionId) return;
        const data = await agentApi.browserScreenshot(sessionId, false);
        if (data && data.image_base64) setScreenshotBase64(data.image_base64);
    };

    const handleQuickScreenshot = async () => {
        const u = quickUrl.trim();
        if (!u || u === 'https://') return;
        setQuickLoading(true);
        setQuickError('');
        setQuickScreenshot('');
        let sid = '';
        try {
            const opened = await agentApi.openBrowserSession({ url: u, headless: true });
            if (!opened?.session_id) throw new Error(opened?.error || 'Failed to open browser session.');
            sid = opened.session_id;
            const shot = await agentApi.browserScreenshot(sid, true);
            if (!shot?.image_base64) throw new Error('No screenshot returned.');
            setQuickScreenshot(shot.image_base64);
        } catch (err) {
            setQuickError(err instanceof Error ? err.message : 'Screenshot failed.');
        } finally {
            if (sid) agentApi.closeBrowserSession(sid).catch(() => {});
            setQuickLoading(false);
        }
    };

    useEffect(() => {
        refreshSessions().catch(() => {});
        if (sessionId) {
            syncState(true).catch(() => {});
        }
        const id = window.setInterval(() => {
            refreshSessions().catch(() => {});
            if (sessionId) syncState(false).catch(() => {});
        }, 3000);
        return () => window.clearInterval(id);
    }, [sessionId]);

    useEffect(() => {
        if (!liveMirror || !sessionId) return undefined;
        let cancelled = false;
        const tick = async () => {
            if (cancelled) return;
            try {
                const data = await agentApi.browserScreenshot(sessionId, false);
                if (!cancelled && data?.image_base64) setScreenshotBase64(data.image_base64);
            } catch {
                /* ignore transient screenshot errors */
            }
        };
        void tick();
        const ms = Math.max(250, Math.min(mirrorMs, 5000));
        const id = window.setInterval(() => void tick(), ms);
        return () => {
            cancelled = true;
            window.clearInterval(id);
        };
    }, [liveMirror, sessionId, mirrorMs]);

    const run = async (
        fn: () => Promise<any>,
        okText: string,
        opts: { refreshState?: boolean; refreshShot?: boolean; withLinks?: boolean } = {},
    ) => {
        setError('');
        setMessage('');
        try {
            const data = await fn();
            if (data && data.success === false) {
                setError(data.error || 'Browser action failed.');
                return;
            }
            setMessage(okText);
            await refreshSessions();
            if (opts.refreshState && sessionId) {
                await syncState(Boolean(opts.withLinks));
            }
            if (opts.refreshShot && sessionId) {
                await capture();
            }
            return data;
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Browser action failed.');
        }
        return null;
    };

    const startAgent = useCallback(() => {
        if (!agentGoal.trim() || agentRunning) return;
        const ctrl = new AbortController();
        agentAbortRef.current = ctrl;
        setAgentRunning(true);
        setAgentSteps([]);
        setAgentScreenshot('');
        setAgentCurrentUrl(agentUrl);

        agentApi.runBrowserAgent(
            agentGoal,
            agentUrl,
            { headless: agentHeadless },
            (event) => {
                setAgentSteps((prev) => [...prev, event]);
                if (event.screenshot) setAgentScreenshot(event.screenshot);
                if (event.url) setAgentCurrentUrl(event.url);
                // scroll log to bottom
                setTimeout(() => {
                    agentLogRef.current?.scrollTo({ top: agentLogRef.current.scrollHeight, behavior: 'smooth' });
                }, 50);
            },
            () => setAgentRunning(false),
            ctrl.signal,
        );
    }, [agentGoal, agentUrl, agentHeadless, agentRunning]);

    const stopAgent = useCallback(() => {
        agentAbortRef.current?.abort();
        setAgentRunning(false);
    }, []);

    const cursorMarkerStyle = useMemo(() => {
        if (!pageState?.cursor || !pageState?.viewport) return null;
        const width = Math.max(1, pageState.viewport.width || 1);
        const height = Math.max(1, pageState.viewport.height || 1);
        const leftPct = (pageState.cursor.x / width) * 100;
        const topPct = (pageState.cursor.y / height) * 100;
        return {
            left: `${Math.max(0, Math.min(100, leftPct))}%`,
            top: `${Math.max(0, Math.min(100, topPct))}%`,
        };
    }, [pageState]);

    const onScreenshotClick = async (evt: MouseEvent<HTMLImageElement>) => {
        if (!sessionId || !pageState?.viewport) return;
        const rect = evt.currentTarget.getBoundingClientRect();
        const relX = (evt.clientX - rect.left) / Math.max(1, rect.width);
        const relY = (evt.clientY - rect.top) / Math.max(1, rect.height);
        const x = Math.round(relX * Math.max(1, pageState.viewport.width));
        const y = Math.round(relY * Math.max(1, pageState.viewport.height));
        setCursorX(x);
        setCursorY(y);
        if (imageClickMode === 'move') {
            await run(
                () => agentApi.browserCursorMove(sessionId, x, y, 1),
                `Cursor moved to (${x}, ${y}).`,
                { refreshState: true, refreshShot: true, withLinks: false },
            );
            return;
        }
        await run(
            () => agentApi.browserCursorClick(sessionId, { x, y }),
            `Clicked at (${x}, ${y}).`,
            { refreshState: true, refreshShot: true, withLinks: true },
        );
    };

    return (
        <div className="h-full overflow-auto space-y-4 p-5 md:p-8">
            <PageHeader
                title="Agent Browser"
                description="AI-controlled browser — give it a goal and it navigates, clicks, and types on its own. Manual controls below for direct access."
            />

            {/* ── AI Agent Panel ─────────────────────────────────────── */}
            <div className="border border-surface-4 bg-surface-1 p-4 space-y-3">
                <h2 className="text-sm font-semibold text-text-primary">AI Agent</h2>
                <div className="flex gap-2">
                    <input
                        className="flex-1 border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                        placeholder="Goal — e.g. 'Search for the latest qwen3 release on GitHub'"
                        value={agentGoal}
                        onChange={(e) => setAgentGoal(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && startAgent()}
                        disabled={agentRunning}
                    />
                    <input
                        className="w-56 border border-surface-4 bg-surface-2 px-3 py-1.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                        placeholder="Start URL"
                        value={agentUrl}
                        onChange={(e) => setAgentUrl(e.target.value)}
                        disabled={agentRunning}
                    />
                    <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={agentHeadless}
                            onChange={(e) => setAgentHeadless(e.target.checked)}
                            disabled={agentRunning}
                            className="accent-accent-blue"
                        />
                        headless
                    </label>
                    {agentRunning ? (
                        <button
                            onClick={stopAgent}
                            className="flex items-center gap-1.5 border border-accent-red bg-accent-red/10 px-3 py-1.5 text-xs text-accent-red hover:bg-accent-red/20"
                        >
                            <Square size={12} /> Stop
                        </button>
                    ) : (
                        <button
                            onClick={startAgent}
                            disabled={!agentGoal.trim()}
                            className="flex items-center gap-1.5 border border-accent-blue bg-accent-blue/10 px-3 py-1.5 text-xs text-accent-blue hover:bg-accent-blue/20 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            <Play size={12} /> Run Agent
                        </button>
                    )}
                </div>

                {(agentSteps.length > 0 || agentRunning) && (
                    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                        {/* Live screenshot */}
                        <div className="border border-surface-4 bg-surface-2">
                            {agentCurrentUrl && (
                                <div className="border-b border-surface-4 px-3 py-1 text-xs text-text-muted truncate">
                                    {agentCurrentUrl}
                                </div>
                            )}
                            {agentScreenshot ? (
                                <img
                                    src={`data:image/png;base64,${agentScreenshot}`}
                                    alt="Agent browser view"
                                    className="w-full object-contain"
                                />
                            ) : (
                                <div className="flex h-40 items-center justify-center text-xs text-text-muted">
                                    {agentRunning ? 'Opening browser…' : 'No screenshot yet'}
                                </div>
                            )}
                        </div>

                        {/* Step log */}
                        <div
                            ref={agentLogRef}
                            className="max-h-96 overflow-y-auto border border-surface-4 bg-surface-2 p-3 space-y-2 text-xs font-mono"
                        >
                            {agentSteps.map((s, i) => (
                                <div key={i} className={`border-l-2 pl-2 ${
                                    s.type === 'done' ? 'border-accent-green text-accent-green' :
                                    s.type === 'error' ? 'border-accent-red text-accent-red' :
                                    s.type === 'stopped' ? 'border-accent-amber text-accent-amber' :
                                    s.type === 'opened' ? 'border-accent-blue text-text-secondary' :
                                    'border-surface-4 text-text-secondary'
                                }`}>
                                    {s.type === 'opened' && <span>Opened: {s.url}</span>}
                                    {s.type === 'step' && (
                                        <span>
                                            <span className="text-text-muted">#{s.step} [{s.action}] </span>
                                            {s.thought}
                                        </span>
                                    )}
                                    {s.type === 'error' && <span>Error: {s.error}</span>}
                                    {s.type === 'done' && <span>Done: {s.result}</span>}
                                    {s.type === 'stopped' && <span>Stopped: {s.reason}</span>}
                                </div>
                            ))}
                            {agentRunning && (
                                <div className="border-l-2 border-accent-blue pl-2 text-accent-blue animate-pulse">
                                    thinking…
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Quick Screenshot — one-click capture */}
            <section className="rounded-card border border-accent-blue/30 bg-surface-1 p-4 space-y-3">
                <div className="flex items-center gap-2">
                    <Camera size={15} className="text-accent-blue shrink-0" />
                    <h2 className="text-sm font-semibold text-text-primary">Quick Screenshot</h2>
                    <span className="text-xs text-text-muted">— enter a URL and capture the full page in one click</span>
                </div>
                <div className="flex flex-wrap gap-2">
                    <input
                        value={quickUrl}
                        onChange={(e) => setQuickUrl(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') void handleQuickScreenshot(); }}
                        placeholder="https://antigravity.com"
                        className="flex-1 min-w-[260px] bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-sm text-text-primary"
                    />
                    <button
                        onClick={() => void handleQuickScreenshot()}
                        disabled={quickLoading || !quickUrl.trim() || quickUrl.trim() === 'https://'}
                        className="px-4 py-2 rounded-btn border border-accent-blue/40 bg-accent-blue/10 text-accent-blue text-sm font-medium disabled:opacity-40 hover:bg-accent-blue/20 transition-colors"
                    >
                        {quickLoading ? 'Capturing…' : 'Take Screenshot'}
                    </button>
                </div>
                {quickError && <p className="text-xs text-accent-red">{quickError}</p>}
                {quickScreenshot && (
                    <div className="space-y-1">
                        <p className="text-xs text-text-muted">Screenshot of <span className="text-text-secondary">{quickUrl}</span></p>
                        <img
                            src={`data:image/png;base64,${quickScreenshot}`}
                            alt="Quick screenshot"
                            className="max-h-[500px] w-auto max-w-full border border-surface-4 rounded-btn object-contain"
                        />
                        <button
                            onClick={() => { setQuickScreenshot(''); setQuickUrl('https://'); }}
                            className="text-xs text-text-muted hover:text-accent-red transition-colors"
                        >
                            Clear
                        </button>
                    </div>
                )}
            </section>

            {/* Advanced Session Controls */}
            <section className="rounded-card border border-surface-4 bg-surface-1 overflow-hidden">
                <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-surface-2 transition-colors text-left"
                >
                    {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    Advanced Session Controls
                    <span className="text-xs text-text-muted font-normal">— manual navigation, cursor control, form interaction</span>
                </button>
                {showAdvanced && <div className="p-4 space-y-4 border-t border-surface-4">
            <div className="space-y-3">
                <label className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                    <input
                        type="checkbox"
                        checked={headedMode}
                        onChange={(e) => setHeadedMode(e.target.checked)}
                        className="rounded border-surface-4"
                    />
                    Visible Chromium window (headed) — backend machine; use headless + live mirror below for in-app view.
                </label>
                <label className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                    <input
                        type="checkbox"
                        checked={liveMirror}
                        onChange={(e) => setLiveMirror(e.target.checked)}
                        className="rounded border-surface-4"
                    />
                    Live mirror (Atlas-style): refresh viewport screenshot automatically
                    <input
                        type="number"
                        min={250}
                        max={5000}
                        step={50}
                        value={mirrorMs}
                        onChange={(e) => setMirrorMs(Number(e.target.value) || 900)}
                        className="w-24 bg-surface-0 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                        title="Interval ms"
                    />
                    <span className="text-text-muted">ms</span>
                </label>
                <div className="flex flex-wrap gap-2">
                    <input
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        className="flex-1 min-w-[260px] bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-sm text-text-primary"
                        placeholder="https://..."
                    />
                    <button
                        onClick={() =>
                            run(
                                () =>
                                    agentApi.openBrowserSession({ url, headless: !headedMode }).then((data) => {
                                        if (data?.session_id) setSessionId(data.session_id);
                                        return data;
                                    }),
                                'Browser session opened.',
                                { refreshState: true, refreshShot: true, withLinks: true },
                            )
                        }
                        className="px-3 py-2 rounded-btn border border-accent-green/40 text-accent-green text-sm"
                    >
                        Open Session
                    </button>
                    <button
                        onClick={() =>
                            run(() => agentApi.closeAllBrowserSessions(), 'Closed all sessions.', {
                                refreshState: true,
                                refreshShot: false,
                                withLinks: false,
                            })
                        }
                        className="px-3 py-2 rounded-btn border border-accent-red/40 text-accent-red text-sm"
                    >
                        Close All
                    </button>
                </div>
            </div>

            <div className="grid md:grid-cols-[300px_1fr] gap-4">
                <div className="rounded-card border border-surface-4 bg-surface-1 p-3">
                    <h2 className="text-sm font-semibold text-text-primary">Sessions</h2>
                    <div className="mt-2 space-y-2 max-h-[420px] overflow-auto">
                        {sessions.length === 0 && <p className="text-xs text-text-secondary">No active sessions.</p>}
                        {sessions.map((session) => (
                            <button
                                key={session.session_id}
                                onClick={() => setSessionId(session.session_id)}
                                className={`w-full text-left rounded-btn border p-2 ${
                                    sessionId === session.session_id ? 'border-accent-blue/50 bg-surface-2' : 'border-surface-4 bg-surface-0'
                                }`}
                            >
                                <p className="text-xs text-text-primary">{session.session_id.slice(0, 8)}</p>
                                <p className="text-[11px] text-text-secondary truncate mt-1">{session.url || '(blank)'}</p>
                                <p className="text-[11px] text-text-secondary truncate">{session.title || '(untitled)'}</p>
                            </button>
                        ))}
                    </div>
                </div>

                <div className="rounded-card border border-surface-4 bg-surface-1 p-4 space-y-3">
                    <p className="text-xs text-text-secondary">active session: {sessionId || 'none'}</p>
                    <div className="flex flex-wrap gap-2">
                        <button
                            disabled={!sessionId}
                            onClick={() =>
                                run(() => agentApi.browserNavigate(sessionId, url), 'Navigated.', {
                                    refreshState: true,
                                    refreshShot: true,
                                    withLinks: true,
                                })
                            }
                            className="px-3 py-2 rounded-btn border border-accent-blue/40 text-accent-blue disabled:opacity-40 text-xs"
                        >
                            Navigate
                        </button>
                        <button
                            disabled={!sessionId}
                            onClick={() =>
                                run(
                                    () =>
                                        agentApi.closeBrowserSession(sessionId).then((data) => {
                                            setSessionId('');
                                            setPageState(null);
                                            setLinks([]);
                                            setScreenshotBase64('');
                                            return data;
                                        }),
                                    'Session closed.',
                                    { refreshState: false, refreshShot: false },
                                )
                            }
                            className="px-3 py-2 rounded-btn border border-accent-red/40 text-accent-red disabled:opacity-40 text-xs"
                        >
                            Close Session
                        </button>
                        <button
                            disabled={!sessionId}
                            onClick={() => run(() => syncState(true), 'State refreshed.', { refreshState: false, refreshShot: false })}
                            className="px-3 py-2 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                        >
                            Refresh State
                        </button>
                        <button
                            disabled={!sessionId}
                            onClick={() => run(() => capture(), 'Screenshot captured.', { refreshState: false, refreshShot: false })}
                            className="px-3 py-2 rounded-btn border border-accent-amber/40 text-accent-amber disabled:opacity-40 text-xs"
                        >
                            Capture View
                        </button>
                    </div>

                    <div className="grid md:grid-cols-2 gap-2">
                        <input
                            value={selector}
                            onChange={(e) => setSelector(e.target.value)}
                            className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary"
                            placeholder="selector"
                        />
                        <input
                            value={typeText}
                            onChange={(e) => setTypeText(e.target.value)}
                            className="bg-surface-0 border border-surface-4 rounded-btn px-3 py-2 text-xs text-text-primary"
                            placeholder="text to type"
                        />
                    </div>

                    <div className="flex flex-wrap gap-2">
                        <button
                            disabled={!sessionId}
                            onClick={() =>
                                run(() => agentApi.browserClick(sessionId, selector), 'Selector click sent.', {
                                    refreshState: true,
                                    refreshShot: true,
                                    withLinks: true,
                                })
                            }
                            className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                        >
                            Click
                        </button>
                        <button
                            disabled={!sessionId}
                            onClick={() =>
                                run(() => agentApi.browserType(sessionId, selector, typeText, false), 'Type action sent.', {
                                    refreshState: true,
                                    refreshShot: true,
                                    withLinks: false,
                                })
                            }
                            className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                        >
                            Type
                        </button>
                        <button
                            disabled={!sessionId}
                            onClick={() =>
                                run(
                                    () =>
                                        agentApi.browserExtract(sessionId, selector, 10000).then((data) => {
                                            setExtractText(data.text || '');
                                            return data;
                                        }),
                                    'Extracted text.',
                                    { refreshState: true, refreshShot: false, withLinks: false },
                                )
                            }
                            className="px-3 py-1.5 rounded-btn border border-accent-green/40 text-accent-green disabled:opacity-40 text-xs"
                        >
                            Extract
                        </button>
                    </div>

                    <div className="rounded-card border border-surface-4 bg-surface-0 p-3 space-y-2">
                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="text-xs text-text-secondary">Cursor controls:</span>
                            <input
                                type="number"
                                value={cursorX}
                                onChange={(e) => setCursorX(Number(e.target.value || 0))}
                                className="w-24 bg-surface-1 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                                placeholder="x"
                            />
                            <input
                                type="number"
                                value={cursorY}
                                onChange={(e) => setCursorY(Number(e.target.value || 0))}
                                className="w-24 bg-surface-1 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                                placeholder="y"
                            />
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorMove(sessionId, cursorX, cursorY, 1), 'Cursor moved.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Move
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorClick(sessionId, { x: cursorX, y: cursorY }), 'Cursor click sent.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: true,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-accent-blue/40 text-accent-blue disabled:opacity-40 text-xs"
                            >
                                Click
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorHover(sessionId, { x: cursorX, y: cursorY }), 'Cursor hover sent.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Hover
                            </button>
                        </div>

                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="text-xs text-text-secondary">Wheel scroll:</span>
                            <input
                                type="number"
                                value={scrollStep}
                                onChange={(e) => setScrollStep(Number(e.target.value || 0))}
                                className="w-28 bg-surface-1 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                            />
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorScroll(sessionId, { dy: -Math.abs(scrollStep) }), 'Scrolled up.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Scroll Up
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorScroll(sessionId, { dy: Math.abs(scrollStep) }), 'Scrolled down.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Scroll Down
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorScroll(sessionId, { dx: -Math.abs(scrollStep) / 3, dy: 0 }), 'Scrolled left.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Scroll Left
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserCursorScroll(sessionId, { dx: Math.abs(scrollStep) / 3, dy: 0 }), 'Scrolled right.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Scroll Right
                            </button>
                        </div>

                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="text-xs text-text-secondary">Page scroll (window):</span>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserScrollPage(sessionId, { position: 'top' }), 'Scrolled to top.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Top
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(() => agentApi.browserScrollPage(sessionId, { position: 'bottom' }), 'Scrolled to bottom.', {
                                        refreshState: true,
                                        refreshShot: true,
                                        withLinks: false,
                                    })
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Bottom
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(
                                        () => agentApi.browserScrollPage(sessionId, { delta_y: scrollStep }),
                                        'Page scroll down.',
                                        { refreshState: true, refreshShot: true, withLinks: false },
                                    )
                                }
                                className="px-3 py-1.5 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40 text-xs"
                            >
                                Page ↓
                            </button>
                            <button
                                disabled={!sessionId}
                                onClick={() =>
                                    run(
                                        () => agentApi.browserScrollIntoView(sessionId, selector),
                                        'Scrolled selector into view.',
                                        { refreshState: true, refreshShot: true, withLinks: false },
                                    )
                                }
                                className="px-3 py-1.5 rounded-btn border border-accent-amber/40 text-accent-amber disabled:opacity-40 text-xs"
                            >
                                Into view
                            </button>
                        </div>

                        <div className="rounded-card border border-surface-4 bg-surface-1 p-3 space-y-2">
                            <p className="text-xs font-medium text-text-primary">Forms & keys</p>
                            <div className="flex flex-wrap gap-2 items-center">
                                <input
                                    value={selectValue}
                                    onChange={(e) => setSelectValue(e.target.value)}
                                    className="w-36 bg-surface-0 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                                    placeholder="select value"
                                />
                                <input
                                    value={selectLabel}
                                    onChange={(e) => setSelectLabel(e.target.value)}
                                    className="w-36 bg-surface-0 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                                    placeholder="or label"
                                />
                                <button
                                    disabled={!sessionId}
                                    onClick={() =>
                                        run(
                                            () => agentApi.browserSelect(sessionId, selector, { value: selectValue, label: selectLabel }),
                                            'Select option set.',
                                            { refreshState: true, refreshShot: true, withLinks: false },
                                        )
                                    }
                                    className="px-2 py-1 rounded-btn border border-surface-4 text-xs disabled:opacity-40"
                                >
                                    Select
                                </button>
                                <button
                                    disabled={!sessionId}
                                    onClick={() =>
                                        run(
                                            () => agentApi.browserCheck(sessionId, selector, true),
                                            'Checked.',
                                            { refreshState: true, refreshShot: true, withLinks: false },
                                        )
                                    }
                                    className="px-2 py-1 rounded-btn border border-surface-4 text-xs disabled:opacity-40"
                                >
                                    Check
                                </button>
                                <button
                                    disabled={!sessionId}
                                    onClick={() =>
                                        run(
                                            () => agentApi.browserCheck(sessionId, selector, false),
                                            'Unchecked.',
                                            { refreshState: true, refreshShot: true, withLinks: false },
                                        )
                                    }
                                    className="px-2 py-1 rounded-btn border border-surface-4 text-xs disabled:opacity-40"
                                >
                                    Uncheck
                                </button>
                            </div>
                            <div className="flex flex-wrap gap-2 items-center">
                                <input
                                    value={pressKey}
                                    onChange={(e) => setPressKey(e.target.value)}
                                    className="w-28 bg-surface-0 border border-surface-4 rounded-btn px-2 py-1 text-xs text-text-primary"
                                    placeholder="Tab"
                                />
                                <button
                                    disabled={!sessionId}
                                    onClick={() =>
                                        run(
                                            () => agentApi.browserPressKey(sessionId, pressKey, selector || ''),
                                            'Key sent.',
                                            { refreshState: true, refreshShot: true, withLinks: false },
                                        )
                                    }
                                    className="px-2 py-1 rounded-btn border border-surface-4 text-xs disabled:opacity-40"
                                >
                                    Press key
                                </button>
                                <button
                                    disabled={!sessionId}
                                    onClick={() =>
                                        run(
                                            () => agentApi.browserWaitFor(sessionId, selector),
                                            'Element ready.',
                                            { refreshState: true, refreshShot: true, withLinks: false },
                                        )
                                    }
                                    className="px-2 py-1 rounded-btn border border-accent-blue/40 text-accent-blue text-xs disabled:opacity-40"
                                >
                                    Wait visible
                                </button>
                                <button
                                    disabled={!sessionId}
                                    onClick={() =>
                                        run(
                                            () =>
                                                agentApi.getBrowserInteractive(sessionId, 100).then((data) => {
                                                    setInteractiveFields(Array.isArray(data.fields) ? data.fields : []);
                                                    return data;
                                                }),
                                            'Interactive snapshot loaded.',
                                            { refreshState: true, refreshShot: false, withLinks: false },
                                        )
                                    }
                                    className="px-2 py-1 rounded-btn border border-accent-green/40 text-accent-green text-xs disabled:opacity-40"
                                >
                                    List fields
                                </button>
                            </div>
                        </div>

                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="text-xs text-text-secondary">Screenshot click mode:</span>
                            <button
                                onClick={() => setImageClickMode('click')}
                                className={`px-2 py-1 text-xs rounded-btn border ${
                                    imageClickMode === 'click' ? 'border-accent-blue/50 text-accent-blue' : 'border-surface-4 text-text-secondary'
                                }`}
                            >
                                Click
                            </button>
                            <button
                                onClick={() => setImageClickMode('move')}
                                className={`px-2 py-1 text-xs rounded-btn border ${
                                    imageClickMode === 'move' ? 'border-accent-blue/50 text-accent-blue' : 'border-surface-4 text-text-secondary'
                                }`}
                            >
                                Move
                            </button>
                        </div>
                    </div>

                    {screenshotBase64 && (
                        <div className="relative inline-block border border-surface-4 rounded-btn overflow-hidden max-w-full">
                            <img
                                src={`data:image/png;base64,${screenshotBase64}`}
                                alt="Browser screenshot"
                                onClick={onScreenshotClick}
                                className={`w-auto block cursor-crosshair ${liveMirror ? 'max-h-[min(72vh,880px)]' : 'max-h-[420px]'}`}
                            />
                            {cursorMarkerStyle && (
                                <div
                                    style={cursorMarkerStyle}
                                    className="absolute -translate-x-1/2 -translate-y-1/2 pointer-events-none"
                                >
                                    <div className="w-4 h-4 border border-accent-red rounded-none" />
                                    <div className="w-8 h-px bg-accent-red -mt-2" />
                                    <div className="w-px h-8 bg-accent-red -ml-2 -mt-4" />
                                </div>
                            )}
                        </div>
                    )}

                    {pageState && (
                        <div className="text-xs text-text-secondary bg-surface-0 border border-surface-4 rounded-btn p-3 space-y-1">
                            <p className="truncate">URL: {pageState.url || '(blank)'}</p>
                            <p className="truncate">Title: {pageState.title || '(untitled)'}</p>
                            <p>
                                Cursor: ({Math.round(pageState.cursor?.x || 0)}, {Math.round(pageState.cursor?.y || 0)}) | Scroll: (
                                {Math.round(pageState.scroll?.x || 0)}, {Math.round(pageState.scroll?.y || 0)})
                            </p>
                            <p>
                                Viewport: {Math.round(pageState.viewport?.width || 0)} x {Math.round(pageState.viewport?.height || 0)} | Document:{' '}
                                {Math.round(pageState.document?.width || 0)} x {Math.round(pageState.document?.height || 0)}
                            </p>
                        </div>
                    )}

                    {interactiveFields.length > 0 && (
                        <div className="border border-surface-4 rounded-btn p-3 bg-surface-0 max-h-[220px] overflow-auto">
                            <h3 className="text-xs font-semibold text-text-primary">Interactive fields</h3>
                            <p className="text-[10px] text-text-muted mt-1">Click a row to copy selector into the selector field.</p>
                            <div className="mt-2 space-y-1">
                                {interactiveFields.map((f, idx) => (
                                    <button
                                        key={`${f.selector}-${idx}`}
                                        type="button"
                                        onClick={() => setSelector(f.selector)}
                                        className="w-full text-left rounded-btn border border-surface-4 p-2 text-[10px] hover:bg-surface-2"
                                    >
                                        <span className="font-mono text-text-primary">{f.selector}</span>
                                        <span className="text-text-muted"> · {f.tag}</span>
                                        {f.label ? <span className="block text-text-secondary truncate">{f.label}</span> : null}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {links.length > 0 && (
                        <div className="border border-surface-4 rounded-btn p-3 bg-surface-0">
                            <h3 className="text-xs font-semibold text-text-primary">Detected Links</h3>
                            <div className="mt-2 max-h-[180px] overflow-auto space-y-1">
                                {links.map((link, idx) => (
                                    <div key={`${idx}-${link.href}`} className="text-[11px] border border-surface-4 rounded-btn p-2">
                                        <p className="text-text-primary truncate">{link.text || '(no text)'}</p>
                                        <p className="text-text-secondary truncate">{link.href}</p>
                                        <div className="mt-1 flex gap-2">
                                            <button
                                                disabled={!sessionId}
                                                onClick={() =>
                                                    run(() => agentApi.browserNavigate(sessionId, link.href), 'Link opened.', {
                                                        refreshState: true,
                                                        refreshShot: true,
                                                        withLinks: true,
                                                    })
                                                }
                                                className="px-2 py-1 rounded-btn border border-accent-blue/40 text-accent-blue disabled:opacity-40"
                                            >
                                                Open
                                            </button>
                                            <button
                                                disabled={!sessionId}
                                                onClick={() => {
                                                    setCursorX(Math.round(link.x + Math.max(1, link.width / 2)));
                                                    setCursorY(Math.round(link.y + Math.max(1, link.height / 2)));
                                                }}
                                                className="px-2 py-1 rounded-btn border border-surface-4 text-text-primary disabled:opacity-40"
                                            >
                                                Set Cursor
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {extractText && (
                        <pre className="max-h-[220px] overflow-auto text-xs bg-surface-0 border border-surface-4 p-3 text-text-primary whitespace-pre-wrap">
                            {extractText}
                        </pre>
                    )}
                </div>
            </div>
            </div>}
            </section>

            {message && <p className="text-sm text-accent-green">{message}</p>}
            {error && <p className="text-sm text-accent-red">{error}</p>}
        </div>
    );
}
