import { useCallback, useRef, useState } from 'react';
import { Loader2, Globe, ArrowRight, FileText, RefreshCw } from 'lucide-react';
import * as api from '../lib/agentSpaceApi';

/**
 * Remote Atlas for phones. The desktop Atlas drives an Electron <webview>, which
 * doesn't exist in a mobile browser — so here the browser runs on the LAPTOP
 * (backend headless Playwright session) and the phone just sends URLs/searches
 * and views the rendered screenshot + extracted text. Reuses the existing
 * /browser/sessions API; no Electron required.
 */

function normalizeUrl(input: string): string {
    const t = input.trim();
    if (!t) return '';
    if (/^https?:\/\//i.test(t)) return t;
    // Looks like a domain (has a dot, no spaces) → treat as URL; else search.
    if (/^[^\s]+\.[^\s]{2,}$/.test(t)) return `https://${t}`;
    return `https://duckduckgo.com/?q=${encodeURIComponent(t)}`;
}

function pickImage(resp: unknown): string {
    const r = (resp || {}) as Record<string, unknown>;
    return String(r.image_base64 || r.screenshot || '');
}

function pickText(resp: unknown): string {
    const r = (resp || {}) as Record<string, unknown>;
    return String(r.text || r.content || r.extracted_text || '').trim();
}

export default function AtlasMobile() {
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [image, setImage] = useState('');
    const [pageTitle, setPageTitle] = useState('');
    const [pageUrl, setPageUrl] = useState('');
    const [pageText, setPageText] = useState('');
    const [showText, setShowText] = useState(false);
    const [error, setError] = useState('');
    const sessionRef = useRef('');

    const ensureSession = useCallback(async (): Promise<string> => {
        if (sessionRef.current) return sessionRef.current;
        const s = await api.openBrowserSession({ headless: true, viewport_width: 412, viewport_height: 824 });
        const id = String((s as { session_id?: string })?.session_id || '');
        sessionRef.current = id;
        return id;
    }, []);

    const go = useCallback(async (raw: string) => {
        const url = normalizeUrl(raw);
        if (!url) return;
        setLoading(true);
        setError('');
        setShowText(false);
        setPageText('');
        try {
            const id = await ensureSession();
            if (!id) throw new Error('Could not start a browser session on the laptop.');
            const state = await api.browserNavigate(id, url);
            setPageTitle(String((state as { title?: string })?.title || ''));
            setPageUrl(String((state as { url?: string })?.url || url));
            const img = pickImage(state);
            if (img) {
                setImage(img);
            } else {
                const shot = await api.browserScreenshot(id, false);
                setImage(pickImage(shot));
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not load that page.');
        } finally {
            setLoading(false);
        }
    }, [ensureSession]);

    const readPage = useCallback(async () => {
        if (!sessionRef.current) return;
        setLoading(true);
        setError('');
        try {
            const r = await api.browserExtract(sessionRef.current, 'body', 8000);
            setPageText(pickText(r) || 'No readable text found on this page.');
            setShowText(true);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Could not read the page.');
        } finally {
            setLoading(false);
        }
    }, []);

    return (
        <div className="flex h-full min-h-0 flex-col bg-surface-0 text-text-primary">
            <form
                onSubmit={(e) => { e.preventDefault(); go(input); }}
                className="flex shrink-0 items-center gap-2 border-b border-surface-5 bg-surface-1 px-3 py-2"
            >
                <Globe className="h-4 w-4 shrink-0 text-text-muted" aria-hidden />
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    inputMode="url"
                    autoCapitalize="off"
                    autoCorrect="off"
                    placeholder="Enter a URL or search…"
                    aria-label="URL or search"
                    className="min-w-0 flex-1 rounded-btn border border-surface-4 bg-surface-2 px-2.5 py-2 text-text-primary outline-none focus:border-accent"
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    aria-label="Go"
                    className="flex shrink-0 items-center justify-center rounded-btn bg-accent px-3.5 py-2 text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
                >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                </button>
            </form>

            {(pageUrl || error) && (
                <div className="flex shrink-0 items-center gap-2 border-b border-surface-5 bg-surface-0 px-3 py-1.5 text-[11px]">
                    {error ? (
                        <span className="text-accent-red">{error}</span>
                    ) : (
                        <>
                            <span className="min-w-0 flex-1 truncate text-text-secondary" title={pageUrl}>
                                {pageTitle || pageUrl}
                            </span>
                            <button
                                type="button"
                                onClick={() => go(pageUrl)}
                                aria-label="Reload"
                                className="shrink-0 rounded p-2.5 text-text-muted transition-colors hover:bg-surface-3 hover:text-text-secondary"
                            >
                                <RefreshCw className="h-4 w-4" />
                            </button>
                            <button
                                type="button"
                                onClick={readPage}
                                className="flex shrink-0 items-center gap-1.5 rounded-btn border border-surface-4 px-3 py-2 text-text-secondary transition-colors hover:bg-surface-3"
                            >
                                <FileText className="h-3.5 w-3.5" /> Read
                            </button>
                        </>
                    )}
                </div>
            )}

            <div className="min-h-0 flex-1 overflow-auto bg-surface-0">
                {showText ? (
                    <div className="p-3">
                        <button type="button" onClick={() => setShowText(false)} className="mb-2 text-[11px] font-medium text-accent">
                            ← Back to page
                        </button>
                        <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-text-secondary">{pageText}</pre>
                    </div>
                ) : image ? (
                    <img src={`data:image/png;base64,${image}`} alt={pageTitle || 'Page capture'} className="w-full" />
                ) : (
                    <div className="flex h-full flex-col items-center justify-center px-6 text-center text-text-muted">
                        <Globe className="mb-3 h-10 w-10 opacity-25" aria-hidden />
                        <p className="text-sm font-medium text-text-secondary">Atlas — remote browser</p>
                        <p className="mt-1 text-xs leading-relaxed">
                            Your laptop opens the page and sends it here. Enter a URL or a search above to begin.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
