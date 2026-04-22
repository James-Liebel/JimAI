import { useCallback, useEffect, useRef, useState } from 'react';
import {
    Globe, ArrowLeft, ArrowRight, RotateCcw, Send, Square,
    Bot, User, X, Plus, MousePointer2, ListChecks, ChevronRight, FlaskConical,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { fetchWithTimeout, logIssue } from '../lib/api';
import { ATLAS_TASK_CATEGORIES } from '../data/atlasTasks';
import AtlasBenchmarkPanel from '../components/AtlasBenchmarkPanel';

// ── Webview type (Electron-specific element) ─────────────────────────────────
interface AtlasWebview extends HTMLElement {
    loadURL(url: string): Promise<void>;
    executeJavaScript(code: string, userGesture?: boolean): Promise<unknown>;
    sendInputEvent(event: {
        type: 'mouseDown' | 'mouseUp' | 'mouseMove' | 'keyDown' | 'keyUp' | 'char';
        x?: number;
        y?: number;
        button?: 'left' | 'middle' | 'right';
        clickCount?: number;
        keyCode?: string;
        modifiers?: string[];
    }): void;
    // focus() is required before sendInputEvent — events are silently dropped otherwise
    focus(): void;
    goBack(): void;
    goForward(): void;
    reload(): void;
    stop(): void;
    getURL(): string;
    getTitle(): string;
    canGoBack(): boolean;
    canGoForward(): boolean;
    isLoading(): boolean;
    capturePage(rect?: { x: number; y: number; width: number; height: number }): Promise<{ toDataURL(): string }>;
}

// ── Types ────────────────────────────────────────────────────────────────────
interface Tab {
    id: string;
    url: string;
    title: string;
    loading: boolean;
}

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
let _tabSeq = 1;
const newTabId = () => `tab-${++_tabSeq}`;

const WELCOME_CONTENT = 'I can control this browser for you. Try: "Go to Amazon and search for wireless headphones" or "Open GitHub and find the qwen3 repo".';
const freshWelcome = (key = 'welcome'): ChatMessage => ({ id: key, role: 'agent', content: WELCOME_CONTENT });

// ── Backend call ─────────────────────────────────────────────────────────────
async function agentStep(
    message: string,
    url: string,
    title: string,
    pageText: string,
    history: { role: string; content: string }[],
    screenshot?: string,
    actionFeedback?: string,
): Promise<AgentStep> {
    const res = await fetchWithTimeout(
        `${BACKEND}/browser/atlas/chat`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message, url, title, page_text: pageText, history,
                screenshot: screenshot ?? '',
                action_feedback: actionFeedback ?? '',
            }),
        },
        90000,
    );
    if (!res.ok) throw new Error(`Backend error ${res.status}`);
    return res.json() as Promise<AgentStep>;
}

// ── Component ────────────────────────────────────────────────────────────────
export default function BrowserAtlas() {
    // ── Tab state ────────────────────────────────────────────────────────────
    const [tabs, setTabs] = useState<Tab[]>([
        { id: 'tab-1', url: 'https://www.google.com', title: '', loading: false },
    ]);
    const [activeTabId, setActiveTabId] = useState('tab-1');
    const activeTabIdRef = useRef('tab-1');
    const webviewRefs = useRef<Map<string, AtlasWebview>>(new Map());

    // ── Navigation state (active tab) ────────────────────────────────────────
    const [navInput, setNavInput] = useState('https://www.google.com');
    const [canGoBack, setCanGoBack] = useState(false);
    const [canGoForward, setCanGoForward] = useState(false);
    const [loading, setLoading] = useState(false);
    const [pageTitle, setPageTitle] = useState('');

    // ── Chat state ───────────────────────────────────────────────────────────
    const _initMsg = freshWelcome('welcome');
    const [messages, setMessages] = useState<ChatMessage[]>([_initMsg]);
    // messagesRef mirrors messages state synchronously so tab-switch callbacks always read current value
    const messagesRef = useRef<ChatMessage[]>([_initMsg]);
    // Persists each tab's chat messages + agent history when switching away from it
    const tabChatsRef = useRef<Map<string, { messages: ChatMessage[]; history: { role: string; content: string }[] }>>(new Map());

    const [input, setInput] = useState('');
    const [agentRunning, setAgentRunning] = useState(false);
    const [manualMode, setManualMode] = useState(false);
    const [benchmarkMode, setBenchmarkMode] = useState(false);
    const [taskPanelOpen, setTaskPanelOpen] = useState(false);
    const [taskSearch, setTaskSearch] = useState('');
    const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
    const [agentStepInfo, setAgentStepInfo] = useState<{
        step: number;
        phase: 'thinking' | 'acting';
        action?: string;
    } | null>(null);
    const abortRef = useRef(false);
    const historyRef = useRef<{ role: string; content: string }[]>([]);
    const chatRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Scroll chat to bottom whenever messages change
    useEffect(() => {
        chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' });
    }, [messages]);

    // ── Get active webview ───────────────────────────────────────────────────
    // Uses activeTabIdRef (not state) so async agent loops always see the
    // current tab even after a new-window event switches the active tab mid-run.
    const getWv = useCallback((): AtlasWebview | null =>
        webviewRefs.current.get(activeTabIdRef.current) ?? null,
    []);

    // ── Tab operations ───────────────────────────────────────────────────────
    const openNewTab = useCallback((url = 'https://www.google.com') => {
        const id = newTabId();
        // Save current tab's chat before switching away
        tabChatsRef.current.set(activeTabIdRef.current, {
            messages: messagesRef.current,
            history: [...historyRef.current],
        });
        // New tab gets a fresh chat
        const welcome = freshWelcome(`welcome-${id}`);
        messagesRef.current = [welcome];
        setMessages([welcome]);
        historyRef.current = [];
        setTabs(prev => [...prev, { id, url, title: '', loading: false }]);
        setActiveTabId(id);
        activeTabIdRef.current = id;
    }, []);

    const closeTab = useCallback((id: string, e?: React.MouseEvent) => {
        e?.stopPropagation();
        setTabs(prev => {
            if (prev.length === 1) return prev;
            const next = prev.filter(t => t.id !== id);
            if (id === activeTabIdRef.current) {
                const newActive = next[next.length - 1].id;
                // Load the new active tab's stored chat (closing tab's chat is discarded)
                const stored = tabChatsRef.current.get(newActive);
                const newMsgs = stored?.messages ?? [freshWelcome(`welcome-${newActive}`)];
                messagesRef.current = newMsgs;
                setMessages(newMsgs);
                historyRef.current = stored?.history ?? [];
                setActiveTabId(newActive);
                activeTabIdRef.current = newActive;
            }
            tabChatsRef.current.delete(id);
            return next;
        });
    }, []);

    const switchTab = useCallback((id: string) => {
        if (id === activeTabIdRef.current) return;
        // Persist current tab's live chat state before leaving
        tabChatsRef.current.set(activeTabIdRef.current, {
            messages: messagesRef.current,
            history: [...historyRef.current],
        });
        // Restore target tab's chat state
        const stored = tabChatsRef.current.get(id);
        const newMsgs = stored?.messages ?? [freshWelcome(`welcome-${id}`)];
        messagesRef.current = newMsgs;
        setMessages(newMsgs);
        historyRef.current = stored?.history ?? [];
        setActiveTabId(id);
        activeTabIdRef.current = id;
        // Sync nav bar to the newly active webview
        const wv = webviewRefs.current.get(id);
        if (wv) {
            setNavInput(wv.getURL() || '');
            setCanGoBack(wv.canGoBack());
            setCanGoForward(wv.canGoForward());
            setLoading(wv.isLoading());
            setPageTitle(wv.getTitle() || '');
        }
    }, []);

    // ── Bind webview events (called once per webview via callback ref) ────────
    const bindWebview = useCallback((id: string, el: HTMLElement | null) => {
        if (!el) { webviewRefs.current.delete(id); return; }
        if (webviewRefs.current.get(id) === el) return; // already bound
        const wv = el as AtlasWebview;
        webviewRefs.current.set(id, wv);

        const syncActiveNav = () => {
            if (id !== activeTabIdRef.current) return;
            setNavInput(wv.getURL());
            setCanGoBack(wv.canGoBack());
            setCanGoForward(wv.canGoForward());
        };

        wv.addEventListener('did-navigate', () => {
            const url = wv.getURL();
            setTabs(prev => prev.map(t => t.id === id ? { ...t, url } : t));
            syncActiveNav();
        });
        wv.addEventListener('did-navigate-in-page', syncActiveNav);
        wv.addEventListener('page-title-updated', (e) => {
            const title = (e as unknown as { title: string }).title || '';
            setTabs(prev => prev.map(t => t.id === id ? { ...t, title } : t));
            if (id === activeTabIdRef.current) setPageTitle(title);
        });
        wv.addEventListener('did-start-loading', () => {
            setTabs(prev => prev.map(t => t.id === id ? { ...t, loading: true } : t));
            if (id === activeTabIdRef.current) setLoading(true);
        });
        wv.addEventListener('did-stop-loading', () => {
            setTabs(prev => prev.map(t => t.id === id ? { ...t, loading: false } : t));
            if (id === activeTabIdRef.current) { setLoading(false); syncActiveNav(); }
        });
        wv.addEventListener('new-window', (e) => {
            const url = (e as unknown as { url: string }).url;
            if (url?.startsWith('http')) openNewTab(url);
        });
    }, [openNewTab]);

    // ── Navigation helpers ───────────────────────────────────────────────────
    const navigate = useCallback((url?: string) => {
        const wv = getWv();
        if (!wv) return;
        let target = (url ?? navInput).trim();
        if (!target) return;
        if (!target.startsWith('http')) target = `https://${target}`;
        setNavInput(target);
        wv.loadURL(target).catch(() => {});
    }, [navInput, getWv]);

    // ── Page state extraction ────────────────────────────────────────────────
    const getPageState = useCallback(async (): Promise<{ url: string; title: string; pageText: string; screenshot: string }> => {
        const wv = getWv();
        if (!wv) return { url: '', title: '', pageText: '', screenshot: '' };


        const url = wv.getURL();
        const title = wv.getTitle();
        let pageText = '';
        try {
            const raw = await wv.executeJavaScript(`
                (function() {
                    const W = window.innerWidth, H = window.innerHeight;
                    const elems = [...document.querySelectorAll(
                        'a[href], button, input:not([type="hidden"]), select, textarea, ' +
                        '[role="button"], [role="link"], [role="tab"], [role="menuitem"], ' +
                        '[role="option"], [role="checkbox"], [role="radio"], ' +
                        '[jsaction], [jsname], [data-action], [data-tooltip]'
                    )].filter(el => {
                        const r = el.getBoundingClientRect();
                        if (r.width < 4 || r.height < 4) return false;
                        if (r.bottom < 0 || r.top > H || r.right < 0 || r.left > W) return false;
                        const s = window.getComputedStyle(el);
                        return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.1;
                    }).slice(0, 35).map(el => {
                        const r = el.getBoundingClientRect();
                        const x = Math.round(r.left + r.width / 2);
                        const y = Math.round(r.top + r.height / 2);
                        const tag = el.tagName.toLowerCase();
                        const type = el.getAttribute('type') || '';
                        const role = el.getAttribute('role') || '';
                        const label = (
                            (el.innerText || '').trim().replace(/\\s+/g,' ') ||
                            el.getAttribute('aria-label') ||
                            el.getAttribute('data-tooltip') ||
                            el.getAttribute('title') ||
                            el.getAttribute('placeholder') ||
                            el.getAttribute('value') || ''
                        ).slice(0, 50);
                        const href = el.getAttribute('href') || '';
                        const jsname = el.getAttribute('jsname') || '';
                        let kind = type ? tag+'['+type+']' : tag;
                        if (role && role !== tag) kind += '[role='+role+']';
                        if (jsname) kind += '[jsname='+jsname+']';
                        if (el.isContentEditable && tag !== 'input' && tag !== 'textarea') kind += '[editable]';
                        return kind + ' ('+x+','+y+') "'+label+'"' + (href ? ' -> '+href.slice(0,60) : '');
                    });
                    const bodyText = document.body ? document.body.innerText.slice(0, 1500) : '';
                    return JSON.stringify({ bodyText, elems });
                })()
            `) as string;
            const parsed = JSON.parse(raw) as { bodyText: string; elems: string[] };
            pageText = parsed.bodyText
                + '\n\n--- Visible elements (tag (x,y) "label") ---\n'
                + parsed.elems.join('\n');
        } catch { /* cross-origin or CSP — proceed without page text */ }

        // Screenshots are only captured when BROWSER_VISION_ENABLED=True on the backend.
        // Skipping here keeps the step lightweight (no PNG encoding + base64 overhead).
        return { url, title, pageText, screenshot: '' };
    }, [getWv]);

    // ── Execute an agent action on the active webview ────────────────────────
    const executeAction = useCallback(async (action: string, params: Record<string, unknown>) => {
        const wv = getWv();
        if (!wv) return;

        switch (action) {
            case 'navigate': {
                const url = String(params.url ?? '');
                if (url) {
                    setNavInput(url);
                    await wv.loadURL(url).catch(() => {});
                    await new Promise<void>((res) => {
                        const done = () => { wv.removeEventListener('did-stop-loading', done); res(); };
                        wv.addEventListener('did-stop-loading', done);
                        setTimeout(res, 5000);
                    });
                    // Extra settle time for SPAs that render after the load event fires
                    await new Promise((r) => setTimeout(r, 1500));
                }
                break;
            }

            case 'click_xy': {
                const x = Number(params.x ?? 0);
                const y = Number(params.y ?? 0);
                if (x > 0 && y > 0) {
                    // Focus the webview first — sendInputEvent is silently dropped without it
                    wv.focus();
                    await new Promise((r) => setTimeout(r, 80));
                    wv.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 });
                    wv.sendInputEvent({ type: 'mouseUp',   x, y, button: 'left', clickCount: 1 });
                    await new Promise<void>((res) => {
                        const done = () => { wv.removeEventListener('did-stop-loading', done); res(); };
                        wv.addEventListener('did-stop-loading', done);
                        setTimeout(res, 3000);
                    });
                }
                break;
            }

            case 'type_xy': {
                const x = Number(params.x ?? 0);
                const y = Number(params.y ?? 0);
                const text = String(params.text ?? '');
                if (x > 0 && y > 0 && text) {
                    wv.focus();
                    await new Promise((r) => setTimeout(r, 80));
                    wv.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 });
                    wv.sendInputEvent({ type: 'mouseUp',   x, y, button: 'left', clickCount: 1 });
                    await new Promise((r) => setTimeout(r, 200));
                    // Detect element kind and type accordingly.
                    // Returns 'typed' for standard elements, 'canvas' when the active
                    // element is a custom/canvas editor that needs sendInputEvent chars.
                    const typeResult = await wv.executeJavaScript(`
                        (function() {
                            const el = document.activeElement;
                            if (!el) return 'no_focus';
                            el.focus();
                            const isStandard = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
                            if (!isStandard) return 'canvas';
                            if (el.isContentEditable) {
                                document.execCommand('selectAll', false);
                                const ok = document.execCommand('insertText', false, ${JSON.stringify(text)});
                                if (!ok) {
                                    el.textContent = ${JSON.stringify(text)};
                                    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: ${JSON.stringify(text)} }));
                                }
                            } else {
                                document.execCommand('selectAll', false);
                                document.execCommand('insertText', false, ${JSON.stringify(text)});
                            }
                            return 'typed';
                        })()
                    `).catch(() => 'error') as string;

                    if (typeResult === 'canvas') {
                        // Active element is a canvas / custom editor — send real char events
                        for (const ch of text) {
                            wv.sendInputEvent({ type: 'char', keyCode: ch });
                        }
                    }
                    await new Promise((r) => setTimeout(r, 300));
                }
                break;
            }

            case 'click_selector': {
                const sel = String(params.selector ?? '');
                if (sel) {
                    // First try: JS click (works even without Electron focus, handles SPA event systems)
                    const jsClicked = await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return 'not_found';
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            // Dispatch full pointer+mouse event sequence for SPA frameworks
                            ['pointerdown','mousedown','pointerup','mouseup'].forEach(t =>
                                el.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, { bubbles: true, cancelable: true, view: window }))
                            );
                            el.click();
                            return 'clicked';
                        })()
                    `).catch(() => 'error') as string;

                    // Also send hardware-level events via Electron for elements that require real input
                    if (jsClicked !== 'not_found') {
                        const rect = await wv.executeJavaScript(`
                            (function() {
                                const el = document.querySelector(${JSON.stringify(sel)});
                                if (!el) return null;
                                const r = el.getBoundingClientRect();
                                return r.width > 0 && r.height > 0
                                    ? { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
                                    : null;
                            })()
                        `).catch(() => null) as { x: number; y: number } | null;
                        if (rect && rect.x > 0 && rect.y > 0) {
                            wv.focus();
                            await new Promise((r) => setTimeout(r, 60));
                            wv.sendInputEvent({ type: 'mouseDown', x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                            wv.sendInputEvent({ type: 'mouseUp',   x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        }
                    }
                    await new Promise<void>((res) => {
                        const done = () => { wv.removeEventListener('did-stop-loading', done); res(); };
                        wv.addEventListener('did-stop-loading', done);
                        setTimeout(res, 3000);
                    });
                }
                break;
            }

            case 'type': {
                const sel = String(params.selector ?? '');
                const text = String(params.text ?? '');
                if (sel && text) {
                    const rect = await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return null;
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            const r = el.getBoundingClientRect();
                            return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                        })()
                    `).catch(() => null) as { x: number; y: number } | null;

                    if (rect && rect.x > 0 && rect.y > 0) {
                        wv.focus();
                        await new Promise((r) => setTimeout(r, 60));
                        wv.sendInputEvent({ type: 'mouseDown', x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        wv.sendInputEvent({ type: 'mouseUp',   x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        await new Promise((r) => setTimeout(r, 150));
                    }
                    await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return 'not_found';
                            el.focus();
                            document.execCommand('selectAll', false);
                            document.execCommand('insertText', false, ${JSON.stringify(text)});
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
                if (sel && text) {
                    const rect = await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return null;
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            const r = el.getBoundingClientRect();
                            return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                        })()
                    `).catch(() => null) as { x: number; y: number } | null;

                    if (rect && rect.x > 0 && rect.y > 0) {
                        wv.focus();
                        await new Promise((r) => setTimeout(r, 60));
                        wv.sendInputEvent({ type: 'mouseDown', x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        wv.sendInputEvent({ type: 'mouseUp',   x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        await new Promise((r) => setTimeout(r, 150));
                    }
                    await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return 'not_found';
                            el.focus();
                            document.execCommand('selectAll', false);
                            document.execCommand('insertText', false, ${JSON.stringify(text)});
                            el.dispatchEvent(new KeyboardEvent('keydown',  { key: 'Enter', keyCode: 13, bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', keyCode: 13, bubbles: true }));
                            el.dispatchEvent(new KeyboardEvent('keyup',    { key: 'Enter', keyCode: 13, bubbles: true }));
                            return 'submitted';
                        })()
                    `).catch(() => {});
                    await new Promise<void>((res) => {
                        const done = () => { wv.removeEventListener('did-stop-loading', done); res(); };
                        wv.addEventListener('did-stop-loading', done);
                        setTimeout(res, 5000);
                    });
                }
                break;
            }

            case 'type_chars': {
                const text = String(params.text ?? '');
                if (text) {
                    wv.focus();
                    await new Promise((r) => setTimeout(r, 80));
                    for (const ch of text) {
                        wv.sendInputEvent({ type: 'char', keyCode: ch });
                    }
                }
                await new Promise((r) => setTimeout(r, 300));
                break;
            }

            case 'press_key': {
                const key = String(params.key ?? 'Enter');
                wv.focus();
                await new Promise((r) => setTimeout(r, 60));
                wv.sendInputEvent({ type: 'keyDown', keyCode: key });
                wv.sendInputEvent({ type: 'keyUp',   keyCode: key });
                await new Promise((r) => setTimeout(r, 800));
                break;
            }

            case 'trigger_autofill': {
                const sel = String(params.selector ?? '');
                if (sel) {
                    const rect = await wv.executeJavaScript(`
                        (function() {
                            const el = document.querySelector(${JSON.stringify(sel)});
                            if (!el) return null;
                            const r = el.getBoundingClientRect();
                            return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
                        })()
                    `).catch(() => null) as { x: number; y: number } | null;

                    if (rect) {
                        wv.focus();
                        await new Promise((r) => setTimeout(r, 60));
                        wv.sendInputEvent({ type: 'mouseDown', x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        wv.sendInputEvent({ type: 'mouseUp',   x: rect.x, y: rect.y, button: 'left', clickCount: 1 });
                        await new Promise((r) => setTimeout(r, 900));
                        wv.sendInputEvent({ type: 'keyDown', keyCode: 'Down' });
                        wv.sendInputEvent({ type: 'keyUp',   keyCode: 'Down' });
                        await new Promise((r) => setTimeout(r, 200));
                        wv.sendInputEvent({ type: 'keyDown', keyCode: 'Return' });
                        wv.sendInputEvent({ type: 'keyUp',   keyCode: 'Return' });
                        await new Promise((r) => setTimeout(r, 600));
                    }
                }
                break;
            }

            case 'wait':
                await new Promise((r) => setTimeout(r, 2500));
                break;

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
    }, [getWv]);

    // ── Chat helpers ─────────────────────────────────────────────────────────
    const addMsg = useCallback((role: ChatMessage['role'], content: string, actionLabel?: string) => {
        setMessages(prev => {
            const next = [...prev, { id: `${Date.now()}-${Math.random()}`, role, content, actionLabel }];
            messagesRef.current = next;
            return next;
        });
    }, []);

    // ── Agent loop ───────────────────────────────────────────────────────────
    const runAgentLoop = useCallback(async (userMessage: string): Promise<{
        agentSaidDone: boolean;
        stepsUsed: number;
        agentFinalResponse: string;
    }> => {
        abortRef.current = false;
        setAgentRunning(true);
        historyRef.current = [...historyRef.current, { role: 'user', content: userMessage }];

        let agentSaidDone = false;
        let stepsUsed = 0;
        let agentFinalResponse = '';
        // Track page state to detect whether each action had any visible effect
        let prevUrl = '';
        let prevPageSnippet = '';
        let actionFeedback = '';

        for (let step = 0; step < MAX_STEPS; step++) {
            if (abortRef.current) break;
            stepsUsed = step + 1;

            setAgentStepInfo({ step: step + 1, phase: 'thinking' });
            const { url, title, pageText, screenshot } = await getPageState();

            // After the first step, detect whether the previous action changed anything
            if (step > 0) {
                const urlChanged = url !== prevUrl;
                const contentChanged = pageText.slice(0, 300) !== prevPageSnippet;
                if (!urlChanged && !contentChanged) {
                    actionFeedback = 'FEEDBACK: Last action had no visible effect — URL and page content unchanged. Try a different approach (different selector, direct URL navigate, scroll to reveal more, or wait).';
                } else {
                    actionFeedback = '';
                }
            }
            prevUrl = url;
            prevPageSnippet = pageText.slice(0, 300);

            let result: AgentStep;
            try {
                result = await agentStep(userMessage, url, title, pageText, historyRef.current.slice(-10), screenshot, actionFeedback);
            } catch (err) {
                const msg = err instanceof Error ? err.message : 'unknown';
                setAgentStepInfo(null);
                addMsg('system', `Connection error: ${msg}`);
                logIssue('browser_agent', 'connection_error', msg, {
                    step, url, task: userMessage, tab: activeTabId,
                });
                break;
            }

            if (abortRef.current) break;

            const { action = 'talk', params = {}, response = '' } = result;
            setAgentStepInfo({ step: step + 1, phase: 'acting', action });

            if (response) {
                agentFinalResponse = response;
                addMsg('agent', response, action === 'talk' || action === 'done' ? undefined : action);
                historyRef.current = [...historyRef.current, { role: 'agent', content: `[${action}] ${response}` }];
            }

            if (action === 'done') {
                agentSaidDone = true;
                if (response.toLowerCase().includes('cannot')) {
                    logIssue('browser_agent', 'task_failed', response, {
                        step, url, task: userMessage, tab: activeTabId,
                    });
                }
            }

            if (action === 'done' || action === 'talk') break;

            await executeAction(action, params as Record<string, unknown>);
        }

        if (!abortRef.current && !agentSaidDone) {
            const { url } = await getPageState().catch(() => ({ url: '' }));
            logIssue('browser_agent', 'max_steps_reached', `Task did not complete in ${MAX_STEPS} steps`, {
                task: userMessage, url, tab: activeTabId,
                last_actions: historyRef.current.slice(-6).map(h => h.content),
            });
        }

        setAgentStepInfo(null);
        setAgentRunning(false);
        setTimeout(() => inputRef.current?.focus(), 50);
        return { agentSaidDone, stepsUsed, agentFinalResponse };
    }, [getPageState, executeAction, addMsg, activeTabId]);

    const sendMessage = useCallback(() => {
        const msg = input.trim();
        if (!msg || agentRunning) return;
        setInput('');
        addMsg('user', msg);
        void runAgentLoop(msg);
    }, [input, agentRunning, addMsg, runAgentLoop]);

    const runBenchmarkTask = useCallback(async (prompt: string) => {
        addMsg('user', `[Benchmark] ${prompt}`);
        const { agentSaidDone, stepsUsed, agentFinalResponse } = await runAgentLoop(prompt);
        const { url, pageText } = await getPageState();
        return { url, pageText, agentSaidDone, stepsUsed, agentFinalResponse };
    }, [addMsg, runAgentLoop, getPageState]);

    const stopAgent = useCallback(() => {
        abortRef.current = true;
        setAgentRunning(false);
        setAgentStepInfo(null);
    }, []);

    const clearChat = useCallback(() => {
        const reset: ChatMessage = { id: 'welcome-reset', role: 'agent', content: 'Chat cleared. What would you like me to do?' };
        messagesRef.current = [reset];
        setMessages([reset]);
        historyRef.current = [];
        tabChatsRef.current.delete(activeTabIdRef.current);
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

            {/* ── Tab bar ───────────────────────────────────────────────────── */}
            <div className="flex items-end gap-0 border-b border-surface-3 bg-surface-0 px-1 pt-1 shrink-0 overflow-x-auto">
                {tabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => switchTab(tab.id)}
                        className={cn(
                            'group flex items-center gap-1.5 px-3 py-1.5 rounded-t text-[11px] max-w-[160px] min-w-[80px] shrink-0 border border-b-0 transition-colors',
                            tab.id === activeTabId
                                ? 'bg-surface-1 border-surface-3 text-text-primary'
                                : 'bg-surface-0 border-transparent text-text-muted hover:bg-surface-1 hover:text-text-secondary',
                        )}
                        title={tab.title || tab.url}
                    >
                        {tab.loading
                            ? <RotateCcw size={9} className="shrink-0 animate-spin text-accent-blue" />
                            : <Globe size={9} className="shrink-0 opacity-50" />
                        }
                        <span className="truncate flex-1 text-left">
                            {tab.title || new URL(tab.url.startsWith('http') ? tab.url : 'https://new').hostname || 'New tab'}
                        </span>
                        {tabs.length > 1 && (
                            <span
                                role="button"
                                onClick={(e) => closeTab(tab.id, e)}
                                className="shrink-0 opacity-0 group-hover:opacity-60 hover:!opacity-100 hover:text-accent-red transition-opacity"
                            >
                                <X size={9} />
                            </span>
                        )}
                    </button>
                ))}
                <button
                    onClick={() => openNewTab()}
                    className="shrink-0 p-1.5 mb-0.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
                    title="New tab"
                >
                    <Plus size={11} />
                </button>
            </div>

            {/* ── Navigation bar ────────────────────────────────────────────── */}
            <div className="flex items-center gap-1 border-b border-surface-3 bg-surface-1 px-2 py-1.5 shrink-0">
                <button
                    onClick={() => getWv()?.goBack()}
                    disabled={!canGoBack}
                    className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 disabled:opacity-30 transition-colors"
                    title="Back"
                >
                    <ArrowLeft size={13} />
                </button>
                <button
                    onClick={() => getWv()?.goForward()}
                    disabled={!canGoForward}
                    className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 disabled:opacity-30 transition-colors"
                    title="Forward"
                >
                    <ArrowRight size={13} />
                </button>
                <button
                    onClick={() => loading ? getWv()?.stop() : getWv()?.reload()}
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

                {/* ── Webviews (all mounted, active one visible) ───────────── */}
                <div className="flex-1 min-w-0 relative">
                    {tabs.map(tab => (
                        <webview
                            key={tab.id}
                            ref={(el) => bindWebview(tab.id, el as HTMLElement | null)}
                            src={tab.url}
                            partition="persist:atlas"
                            allowpopups
                            style={{
                                position: 'absolute',
                                inset: 0,
                                display: tab.id === activeTabId ? 'flex' : 'none',
                            }}
                        />
                    ))}
                    {/* Manual mode overlay — shows when agent panel is hidden */}
                    {manualMode && (
                        <button
                            onClick={() => setManualMode(false)}
                            className="absolute bottom-3 right-3 z-10 flex items-center gap-1.5 rounded-full border border-accent-blue/40 bg-surface-1/90 backdrop-blur-sm px-3 py-1.5 text-[11px] font-medium text-accent-blue shadow-lg hover:bg-surface-2 transition-colors"
                            title="Return to AI agent"
                        >
                            <Bot size={11} />
                            Resume agent
                        </button>
                    )}
                </div>

                {/* ── Agent chat panel (hidden in manual mode) ─────────────── */}
                <div className={cn(
                    'flex shrink-0 flex-col border-l border-surface-3 bg-surface-1 min-h-0 transition-all duration-200',
                    manualMode ? 'w-0 overflow-hidden border-l-0' : 'w-72',
                )}>

                    {/* Header */}
                    <div className="border-b border-surface-3 px-3 py-2 flex items-center gap-2 shrink-0">
                        <Bot size={13} className="text-accent-blue shrink-0" />
                        <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wide flex-1">
                            AI Agent
                        </span>
                        {agentStepInfo && (
                            <span className={cn(
                                'text-[10px] font-mono animate-pulse',
                                agentStepInfo.phase === 'thinking' ? 'text-accent-amber' : 'text-accent-green',
                            )}>
                                {agentStepInfo.phase === 'thinking'
                                    ? `step ${agentStepInfo.step} · thinking`
                                    : `step ${agentStepInfo.step} · ${agentStepInfo.action}`}
                            </span>
                        )}
                        <button
                            onClick={() => { setTaskPanelOpen(o => !o); setTaskSearch(''); }}
                            className={cn(
                                'p-1 rounded hover:bg-surface-2 transition-colors',
                                taskPanelOpen ? 'text-accent-blue' : 'text-text-muted hover:text-accent-blue',
                            )}
                            title="Task library — 100 pre-built tasks"
                        >
                            <ListChecks size={11} />
                        </button>
                        <button
                            onClick={() => setBenchmarkMode(o => !o)}
                            disabled={agentRunning}
                            className={cn(
                                'p-1 rounded hover:bg-surface-2 transition-colors disabled:opacity-30',
                                benchmarkMode ? 'text-accent-amber' : 'text-text-muted hover:text-accent-amber',
                            )}
                            title="Benchmark mode — run and grade all 100 tasks"
                        >
                            <FlaskConical size={11} />
                        </button>
                        <button
                            onClick={() => { if (!agentRunning) setManualMode(true); }}
                            disabled={agentRunning}
                            className="p-1 rounded text-text-muted hover:text-accent-blue hover:bg-surface-2 disabled:opacity-30 transition-colors"
                            title="Manual mode — browse freely, AI panel hides"
                        >
                            <MousePointer2 size={11} />
                        </button>
                        <button
                            onClick={clearChat}
                            disabled={agentRunning}
                            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-2 disabled:opacity-30 transition-colors"
                            title="Clear chat"
                        >
                            <X size={11} />
                        </button>
                    </div>

                    {/* Benchmark panel (replaces chat when benchmarkMode=true) */}
                    {benchmarkMode && (
                        <AtlasBenchmarkPanel
                            onRunTask={runBenchmarkTask}
                            isAgentRunning={agentRunning}
                            onStop={stopAgent}
                        />
                    )}

                    {/* Messages */}
                    <div ref={chatRef} className={cn('flex-1 overflow-y-auto p-3 space-y-3 min-h-0', benchmarkMode && 'hidden')}>
                        {messages.map((msg) => (
                            <div
                                key={msg.id}
                                className={cn('flex gap-2 items-start', msg.role === 'user' && 'flex-row-reverse')}
                            >
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

                        {agentStepInfo && (
                            <div className="flex gap-2 items-start">
                                <div className={cn(
                                    'shrink-0 w-5 h-5 rounded-full flex items-center justify-center mt-0.5',
                                    agentStepInfo.phase === 'thinking' ? 'bg-accent-amber/15' : 'bg-accent-green/15',
                                )}>
                                    <Bot size={10} className={agentStepInfo.phase === 'thinking' ? 'text-accent-amber' : 'text-accent-green'} />
                                </div>
                                <div className="bg-surface-2 rounded-lg px-2.5 py-1.5 text-[11px] text-text-muted">
                                    {agentStepInfo.phase === 'thinking' ? (
                                        <span className="flex items-center gap-1.5">
                                            <span className="text-accent-amber font-mono">step {agentStepInfo.step}</span>
                                            <span>planning next action</span>
                                            <span className="flex gap-0.5">
                                                <span className="animate-bounce [animation-delay:0ms]">·</span>
                                                <span className="animate-bounce [animation-delay:150ms]">·</span>
                                                <span className="animate-bounce [animation-delay:300ms]">·</span>
                                            </span>
                                        </span>
                                    ) : (
                                        <span className="flex items-center gap-1.5">
                                            <span className="text-accent-green font-mono">step {agentStepInfo.step}</span>
                                            <span className="text-accent-green/80 font-mono text-[10px] bg-accent-green/10 px-1 py-0.5 rounded">
                                                {agentStepInfo.action}
                                            </span>
                                            <span className="flex gap-0.5">
                                                <span className="animate-bounce [animation-delay:0ms]">·</span>
                                                <span className="animate-bounce [animation-delay:150ms]">·</span>
                                                <span className="animate-bounce [animation-delay:300ms]">·</span>
                                            </span>
                                        </span>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ── Task library panel ──────────────────────────────── */}
                    {taskPanelOpen && !benchmarkMode && (
                        <div className="border-t border-surface-3 flex flex-col shrink-0 max-h-64 min-h-0 bg-surface-0">
                            <div className="px-2 pt-2 pb-1 shrink-0">
                                <input
                                    autoFocus
                                    className="w-full border border-surface-4 bg-surface-2 rounded px-2 py-1 text-[11px] text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue"
                                    placeholder="Search 100 tasks…"
                                    value={taskSearch}
                                    onChange={e => { setTaskSearch(e.target.value); setExpandedCategory(null); }}
                                />
                            </div>
                            <div className="overflow-y-auto flex-1 pb-1">
                                {taskSearch.trim() ? (
                                    // Flat filtered results
                                    ATLAS_TASK_CATEGORIES
                                        .flatMap(c => c.tasks.map(t => ({ ...t, categoryName: c.name })))
                                        .filter(t =>
                                            t.label.toLowerCase().includes(taskSearch.toLowerCase()) ||
                                            t.prompt.toLowerCase().includes(taskSearch.toLowerCase())
                                        )
                                        .slice(0, 20)
                                        .map(task => (
                                            <button
                                                key={task.id}
                                                onClick={() => {
                                                    setInput(task.prompt);
                                                    setTaskPanelOpen(false);
                                                    setTaskSearch('');
                                                    setTimeout(() => inputRef.current?.focus(), 50);
                                                }}
                                                className="w-full text-left px-2.5 py-1.5 hover:bg-surface-2 transition-colors"
                                            >
                                                <span className="block text-[10px] text-text-muted font-mono">{task.categoryName}</span>
                                                <span className="block text-[11px] text-text-primary leading-snug">{task.label}</span>
                                            </button>
                                        ))
                                ) : (
                                    // Categorized accordion
                                    ATLAS_TASK_CATEGORIES.map(cat => (
                                        <div key={cat.name}>
                                            <button
                                                onClick={() => setExpandedCategory(p => p === cat.name ? null : cat.name)}
                                                className="w-full flex items-center justify-between px-2.5 py-1.5 hover:bg-surface-2 transition-colors"
                                            >
                                                <span className="text-[11px] font-semibold text-text-secondary">{cat.name}</span>
                                                <span className="flex items-center gap-1">
                                                    <span className="text-[10px] text-text-muted">{cat.tasks.length}</span>
                                                    <ChevronRight
                                                        size={9}
                                                        className={cn('text-text-muted transition-transform', expandedCategory === cat.name && 'rotate-90')}
                                                    />
                                                </span>
                                            </button>
                                            {expandedCategory === cat.name && cat.tasks.map(task => (
                                                <button
                                                    key={task.id}
                                                    onClick={() => {
                                                        setInput(task.prompt);
                                                        setTaskPanelOpen(false);
                                                        setExpandedCategory(null);
                                                        setTimeout(() => inputRef.current?.focus(), 50);
                                                    }}
                                                    className="w-full text-left px-4 py-1 hover:bg-surface-2 transition-colors"
                                                >
                                                    <span className="block text-[11px] text-text-primary leading-snug">{task.label}</span>
                                                </button>
                                            ))}
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    )}

                    {/* Input */}
                    {!benchmarkMode && <div className="border-t border-surface-3 p-2 flex flex-col gap-1 shrink-0">
                        <textarea
                            ref={inputRef}
                            rows={4}
                            className="w-full resize-none border border-surface-4 bg-surface-2 rounded px-2.5 py-1.5 text-[12px] text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-blue transition-colors leading-relaxed"
                            placeholder={agentRunning ? 'Agent running…' : 'Tell the agent what to do…'}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !agentRunning) { e.preventDefault(); sendMessage(); } }}
                            disabled={agentRunning}
                        />
                        <div className="flex justify-end">
                            {agentRunning ? (
                                <button
                                    onClick={stopAgent}
                                    className="p-1.5 rounded border border-accent-red/40 bg-accent-red/10 text-accent-red hover:bg-accent-red/20 transition-colors"
                                    title="Stop agent"
                                >
                                    <Square size={13} />
                                </button>
                            ) : (
                                <button
                                    onClick={sendMessage}
                                    disabled={!input.trim()}
                                    className="p-1.5 rounded border border-accent-blue/50 bg-accent-blue/10 text-accent-blue hover:bg-accent-blue/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    title="Send (Enter)"
                                >
                                    <Send size={13} />
                                </button>
                            )}
                        </div>
                    </div>}
                </div>
            </div>
        </div>
    );
}
