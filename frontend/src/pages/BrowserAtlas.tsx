import { useCallback, useEffect, useRef, useState } from 'react';
import {
    Globe, ArrowLeft, ArrowRight, RotateCcw, Send, Square,
    Bot, User, X,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchWithTimeout } from '../lib/api';

// ── Webview type (Electron-specific element) ─────────────────────────────────
interface AtlasWebview extends HTMLElement {
    loadURL(url: string): Promise<void>;
    executeJavaScript(code: string, userGesture?: boolean): Promise<unknown>;
    goBack(): void;
    goForward(): void;
    reload(): void;
    stop(): void;
    getURL(): string;
    getTitle(): string;
    canGoBack(): boolean;
    canGoForward(): boolean;
    isLoading(): boolean;
}


// ── Types ────────────────────────────────────────────────────────────────────
interface ChatMessage {
    id: string;
    role: 'user' | 'agent' | 'system';
    content: string;
    actionLabel?: string;
}

interface AgentStep {
    thought?: string;
    action?: string;
    params?: Record<string, unknown>;
    response?: string;
}

const BACKEND = 'http://127.0.0.1:8000/api/agent-space';
const MAX_STEPS = 15;
const isElectron = navigator.userAgent.includes('Electron');

// ── Backend call ─────────────────────────────────────────────────────────────
async function agentStep(
    message: string,
    url: string,
    title: string,
    pageText: string,
    history: { role: string; content: string }[],
): Promise<AgentStep> {
    const res = await fetchWithTimeout(
        `${BACKEND}/browser/atlas/chat`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, url, title, page_text: pageText, history }),
        },
        30000,
    );
    if (!res.ok) throw new Error(`Backend error ${res.status}`);
    return res.json() as Promise<AgentStep>;
}

// ── Component ────────────────────────────────────────────────────────────────
export default function BrowserAtlas() {
    const webviewRef = useRef<AtlasWebview>(null);

    // Navigation state
    const [navInput, setNavInput] = useState('https://www.google.com');
    const [pageTitle, setPageTitle] = useState('');
    const [canGoBack, setCanGoBack] = useState(false);
    const [canGoForward, setCanGoForward] = useState(false);
    const [loading, setLoading] = useState(false);

    // Chat state
    const [messages, setMessages] = useState<ChatMessage[]>([
        {
            id: 'welcome',
            role: 'agent',
            content:
                'I can control this browser for you. Try: "Go to Amazon and search for wireless headphones" or "Open GitHub and find the qwen3 repo".',
        },
    ]);
    const [input, setInput] = useState('');
    const [agentRunning, setAgentRunning] = useState(false);
    const abortRef = useRef(false);
    const historyRef = useRef<{ role: string; content: string }[]>([]);
    const chatRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Scroll chat to bottom whenever messages change
    useEffect(() => {
        chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' });
    }, [messages]);

    // ── Wire webview events ──────────────────────────────────────────────────
    useEffect(() => {
        const wv = webviewRef.current;
        if (!wv || !isElectron) return;

        const updateNav = () => {
            const url = wv.getURL();
            setNavInput(url);
            setCanGoBack(wv.canGoBack());
            setCanGoForward(wv.canGoForward());
        };

        const onTitleUpdated = (e: unknown) => {
            setPageTitle((e as { title: string }).title || '');
        };

        const onStartLoading = () => setLoading(true);
        const onStopLoading = () => { setLoading(false); updateNav(); };

        wv.addEventListener('did-navigate', updateNav);
        wv.addEventListener('did-navigate-in-page', updateNav);
        wv.addEventListener('page-title-updated', onTitleUpdated);
        wv.addEventListener('did-start-loading', onStartLoading);
        wv.addEventListener('did-stop-loading', onStopLoading);

        return () => {
            wv.removeEventListener('did-navigate', updateNav);
            wv.removeEventListener('did-navigate-in-page', updateNav);
            wv.removeEventListener('page-title-updated', onTitleUpdated);
            wv.removeEventListener('did-start-loading', onStartLoading);
            wv.removeEventListener('did-stop-loading', onStopLoading);
        };
    }, []);

    // ── Navigation helpers ───────────────────────────────────────────────────
    const navigate = useCallback((url?: string) => {
        const wv = webviewRef.current;
        if (!wv) return;
        let target = (url ?? navInput).trim();
        if (!target) return;
        if (!target.startsWith('http')) target = `https://${target}`;
        setNavInput(target);
        wv.loadURL(target).catch(() => {});
    }, [navInput]);

    // ── Page state extraction ────────────────────────────────────────────────
    const getPageState = useCallback(async (): Promise<{ url: string; title: string; pageText: string }> => {
        const wv = webviewRef.current;
        if (!wv) return { url: '', title: '', pageText: '' };

        const url = wv.getURL();
        const title = wv.getTitle();
        let pageText = '';
        try {
            const raw = await wv.executeJavaScript(`
                (function() {
                    const text = (document.body && document.body.innerText) ? document.body.innerText.slice(0, 3500) : '';
                    const links = [...document.querySelectorAll('a[href]')]
                        .slice(0, 40)
                        .map(a => (a.innerText || '').trim().slice(0, 60) + ' → ' + a.href)
                        .filter(Boolean)
                        .join('\\n');
                    const inputs = [...document.querySelectorAll('input,select,textarea,button')]
                        .slice(0, 30)
                        .map(el => {
                            const tag = el.tagName.toLowerCase();
                            const name = el.id ? '#' + el.id : (el.name ? '[name="' + el.name + '"]' : '');
                            const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.innerText || '';
                            return tag + (name ? name : '') + (label ? ' "' + label.slice(0,40) + '"' : '');
                        })
                        .join(', ');
                    return JSON.stringify({ text, links, inputs });
                })()
            `) as string;
            const parsed = JSON.parse(raw) as { text: string; links: string; inputs: string };
            pageText = `${parsed.text}\n\n--- Links ---\n${parsed.links}\n\n--- Interactive ---\n${parsed.inputs}`;
        } catch { /* cross-origin or CSP block — proceed without page text */ }

        return { url, title, pageText };
    }, []);

    // ── Execute an agent action on the webview ───────────────────────────────
    const executeAction = useCallback(async (action: string, params: Record<string, unknown>) => {
        const wv = webviewRef.current;
        if (!wv) return;

        switch (action) {
            case 'navigate': {
                const url = String(params.url ?? '');
                if (url) {
                    setNavInput(url);
                    await wv.loadURL(url).catch(() => {});
                    // Wait for page to settle
                    await new Promise<void>((res) => {
                        const done = () => { wv.removeEventListener('did-stop-loading', done); res(); };
                        wv.addEventListener('did-stop-loading', done);
                        setTimeout(res, 5000); // fallback timeout
                    });
                }
                break;
            }

            case 'click_selector': {
                const sel = String(params.selector ?? '');
                if (sel) {
                    await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return 'not_found';
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            el.click();
                            return 'clicked';
                        })()
                    `).catch(() => {});
                    await new Promise((r) => setTimeout(r, 1200));
                }
                break;
            }

            case 'type': {
                const sel = String(params.selector ?? '');
                const text = String(params.text ?? '');
                if (sel) {
                    await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return 'not_found';
                            el.focus();
                            el.value = ${JSON.stringify(text)};
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return 'typed';
                        })()
                    `).catch(() => {});
                    await new Promise((r) => setTimeout(r, 400));
                }
                break;
            }

            case 'type_and_submit': {
                const sel = String(params.selector ?? '');
                const text = String(params.text ?? '');
                if (sel) {
                    await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return 'not_found';
                            el.focus();
                            el.value = ${JSON.stringify(text)};
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', keyCode: 13, bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', keyCode: 13, bubbles: true }));
                            if (el.form) el.form.submit();
                            return 'submitted';
                        })()
                    `).catch(() => {});
                    await new Promise<void>((res) => {
                        const done = () => { wv.removeEventListener('did-stop-loading', done); res(); };
                        wv.addEventListener('did-stop-loading', done);
                        setTimeout(res, 4000);
                    });
                }
                break;
            }

            case 'scroll': {
                const dy = Number(params.dy ?? 400);
                await wv.executeJavaScript(`window.scrollBy({ top: ${dy}, behavior: 'smooth' })`).catch(() => {});
                await new Promise((r) => setTimeout(r, 500));
                break;
            }

            case 'js': {
                const code = String(params.code ?? '');
                if (code) await wv.executeJavaScript(code).catch(() => {});
                await new Promise((r) => setTimeout(r, 600));
                break;
            }
        }
    }, []);

    // ── Chat helpers ─────────────────────────────────────────────────────────
    const addMsg = useCallback((role: ChatMessage['role'], content: string, actionLabel?: string) => {
        setMessages((prev) => [
            ...prev,
            { id: `${Date.now()}-${Math.random()}`, role, content, actionLabel },
        ]);
    }, []);

    // ── Agent loop ───────────────────────────────────────────────────────────
    const runAgentLoop = useCallback(async (userMessage: string) => {
        abortRef.current = false;
        setAgentRunning(true);
        historyRef.current = [...historyRef.current, { role: 'user', content: userMessage }];

        for (let step = 0; step < MAX_STEPS; step++) {
            if (abortRef.current) break;

            const { url, title, pageText } = await getPageState();

            let result: AgentStep;
            try {
                result = await agentStep(userMessage, url, title, pageText, historyRef.current.slice(-10));
            } catch (err) {
                addMsg('system', `Connection error: ${err instanceof Error ? err.message : 'unknown'}`);
                break;
            }

            if (abortRef.current) break;

            const { action = 'talk', params = {}, response = '' } = result;

            if (response) {
                addMsg('agent', response, action === 'talk' || action === 'done' ? undefined : action);
                historyRef.current = [...historyRef.current, { role: 'agent', content: response }];
            }

            if (action === 'done' || action === 'talk') break;

            await executeAction(action, params as Record<string, unknown>);
        }

        setAgentRunning(false);
        setTimeout(() => inputRef.current?.focus(), 50);
    }, [getPageState, executeAction, addMsg]);

    const sendMessage = useCallback(() => {
        const msg = input.trim();
        if (!msg || agentRunning) return;
        setInput('');
        addMsg('user', msg);
        void runAgentLoop(msg);
    }, [input, agentRunning, addMsg, runAgentLoop]);

    const stopAgent = useCallback(() => {
        abortRef.current = true;
        setAgentRunning(false);
    }, []);

    const clearChat = useCallback(() => {
        setMessages([{
            id: 'welcome-reset',
            role: 'agent',
            content: 'Chat cleared. What would you like me to do?',
        }]);
        historyRef.current = [];
    }, []);

    // ── Non-Electron fallback ─────────────────────────────────────────────────
    if (!isElectron) {
        return (
            <div className="flex h-full items-center justify-center flex-col gap-3 text-text-muted">
                <Globe size={48} className="opacity-20" />
                <p className="text-sm font-medium">Atlas Browser requires the desktop app.</p>
                <p className="text-xs opacity-60">Open JimAI in Electron to use this feature.</p>
            </div>
        );
    }

    // ── Render ────────────────────────────────────────────────────────────────
    return (
        <div className="flex h-full flex-col bg-surface-0 overflow-hidden">

            {/* ── Top bar ───────────────────────────────────────────────────── */}
            <div className="flex items-center gap-1 border-b border-surface-3 bg-surface-1 px-2 py-1.5 shrink-0">
                <Globe size={13} className="text-accent-blue mx-1 shrink-0" />

                <button
                    onClick={() => webviewRef.current?.goBack()}
                    disabled={!canGoBack}
                    className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 disabled:opacity-30 transition-colors"
                    title="Back"
                >
                    <ArrowLeft size={13} />
                </button>
                <button
                    onClick={() => webviewRef.current?.goForward()}
                    disabled={!canGoForward}
                    className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 disabled:opacity-30 transition-colors"
                    title="Forward"
                >
                    <ArrowRight size={13} />
                </button>
                <button
                    onClick={() => loading ? webviewRef.current?.stop() : webviewRef.current?.reload()}
                    className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
                    title={loading ? 'Stop' : 'Reload'}
                >
                    <RotateCcw size={12} className={cn(loading && 'animate-spin')} />
                </button>

                <form
                    className="flex flex-1 items-center mx-1"
                    onSubmit={(e) => { e.preventDefault(); navigate(); }}
                >
                    <input
                        className="w-full border border-surface-4 bg-surface-2 rounded px-3 py-1 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue transition-colors"
                        value={navInput}
                        onChange={(e) => setNavInput(e.target.value)}
                        placeholder="Search or enter URL"
                        spellCheck={false}
                    />
                </form>

                {pageTitle && (
                    <span className="text-[11px] text-text-muted truncate max-w-40 hidden xl:block" title={pageTitle}>
                        {pageTitle}
                    </span>
                )}
            </div>

            {/* ── Main area ─────────────────────────────────────────────────── */}
            <div className="flex flex-1 overflow-hidden min-h-0">

                {/* ── Webview ─────────────────────────────────────────────── */}
                <webview
                    ref={webviewRef as React.RefObject<HTMLElement>}
                    src="https://www.google.com"
                    partition="persist:atlas"
                    allowpopups
                    style={{
                        flex: 1,
                        minWidth: 0,
                        height: '100%',
                        display: 'flex',
                    }}
                />

                {/* ── Agent chat panel ────────────────────────────────────── */}
                <div className="flex w-72 shrink-0 flex-col border-l border-surface-3 bg-surface-1 min-h-0">

                    {/* Header */}
                    <div className="border-b border-surface-3 px-3 py-2 flex items-center gap-2 shrink-0">
                        <Bot size={13} className="text-accent-blue shrink-0" />
                        <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wide flex-1">
                            AI Agent
                        </span>
                        {agentRunning && (
                            <span className="text-[10px] text-accent-blue animate-pulse">running…</span>
                        )}
                        <button
                            onClick={clearChat}
                            disabled={agentRunning}
                            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 disabled:opacity-30 transition-colors"
                            title="Clear chat"
                        >
                            <X size={11} />
                        </button>
                    </div>

                    {/* Messages */}
                    <div
                        ref={chatRef}
                        className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0"
                    >
                        {messages.map((msg) => (
                            <div
                                key={msg.id}
                                className={cn(
                                    'flex gap-2 items-start',
                                    msg.role === 'user' && 'flex-row-reverse',
                                )}
                            >
                                {/* Avatar */}
                                <div className={cn(
                                    'shrink-0 w-5 h-5 rounded-full flex items-center justify-center mt-0.5',
                                    msg.role === 'agent' && 'bg-accent-blue/15',
                                    msg.role === 'user' && 'bg-surface-3',
                                    msg.role === 'system' && 'bg-accent-amber/15',
                                )}>
                                    {msg.role === 'agent' && <Bot size={10} className="text-accent-blue" />}
                                    {msg.role === 'user' && <User size={10} className="text-text-muted" />}
                                    {msg.role === 'system' && <span className="text-[8px] text-accent-amber">!</span>}
                                </div>

                                {/* Bubble */}
                                <div className={cn(
                                    'rounded-lg px-2.5 py-1.5 text-[12px] leading-relaxed max-w-[200px]',
                                    msg.role === 'agent' && 'bg-surface-2 text-text-secondary',
                                    msg.role === 'user' && 'bg-accent-blue/15 text-text-primary',
                                    msg.role === 'system' && 'bg-surface-3 text-text-muted font-mono text-[10px]',
                                )}>
                                    {msg.actionLabel && (
                                        <span className="block text-[10px] text-accent-blue/60 font-mono mb-1">
                                            [{msg.actionLabel}]
                                        </span>
                                    )}
                                    {msg.content}
                                </div>
                            </div>
                        ))}

                        {agentRunning && (
                            <div className="flex gap-2 items-start">
                                <div className="shrink-0 w-5 h-5 rounded-full bg-accent-blue/15 flex items-center justify-center mt-0.5">
                                    <Bot size={10} className="text-accent-blue" />
                                </div>
                                <div className="bg-surface-2 rounded-lg px-2.5 py-1.5 text-[12px] text-text-muted flex gap-1">
                                    <span className="animate-bounce [animation-delay:0ms]">·</span>
                                    <span className="animate-bounce [animation-delay:150ms]">·</span>
                                    <span className="animate-bounce [animation-delay:300ms]">·</span>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Input */}
                    <div className="border-t border-surface-3 p-2 flex gap-1.5 shrink-0">
                        <input
                            ref={inputRef}
                            className="flex-1 border border-surface-4 bg-surface-2 rounded px-2.5 py-1.5 text-[12px] text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue transition-colors min-w-0"
                            placeholder={agentRunning ? 'Agent running…' : 'Tell the agent what to do…'}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !agentRunning) sendMessage(); }}
                            disabled={agentRunning}
                        />
                        {agentRunning ? (
                            <button
                                onClick={stopAgent}
                                className="shrink-0 p-1.5 rounded border border-accent-red/40 bg-accent-red/10 text-accent-red hover:bg-accent-red/20 transition-colors"
                                title="Stop agent"
                            >
                                <Square size={13} />
                            </button>
                        ) : (
                            <button
                                onClick={sendMessage}
                                disabled={!input.trim()}
                                className="shrink-0 p-1.5 rounded border border-accent-blue/50 bg-accent-blue/10 text-accent-blue hover:bg-accent-blue/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                title="Send (Enter)"
                            >
                                <Send size={13} />
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
