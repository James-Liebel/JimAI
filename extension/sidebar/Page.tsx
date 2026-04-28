import React, { useState } from 'react';
import { streamChat } from './lib/api';

const styles: Record<string, React.CSSProperties> = {
    container: { display: 'flex', flexDirection: 'column', height: '100%' },
    actions: { padding: '12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', borderBottom: '1px solid #1e1e24' },
    btn: {
        padding: '10px 8px', background: '#111114', border: '1px solid #1e1e24',
        color: '#e8e8f0', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
        textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
    },
    btnEmoji: { fontSize: '16px' },
    output: { flex: 1, overflowY: 'auto', padding: '12px', fontSize: '12px', lineHeight: '1.55', whiteSpace: 'pre-wrap', color: '#e8e8f0' },
    placeholder: { color: '#55556A', fontSize: '12px', textAlign: 'center', padding: '32px 16px' },
    status: { padding: '8px 12px', fontSize: '11px', color: '#7070a0', borderTop: '1px solid #1e1e24' },
    busy: { color: '#3B82F6' },
    error: { color: '#EF4444' },
};

const MAX_PAGE_TEXT = 8000;

async function getActiveTab(): Promise<chrome.tabs.Tab | null> {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab || null;
}

async function getPageText(): Promise<{ text: string; url: string; title: string } | null> {
    const tab = await getActiveTab();
    if (!tab?.id) return null;
    return new Promise((resolve) => {
        chrome.tabs.sendMessage(
            tab.id!,
            { type: 'CAPTURE_REQUEST' },
            (resp: { text?: string } | undefined) => {
                if (chrome.runtime.lastError || !resp?.text) {
                    resolve(null);
                    return;
                }
                resolve({
                    text: resp.text.slice(0, MAX_PAGE_TEXT),
                    url: tab.url || '',
                    title: tab.title || '',
                });
            },
        );
    });
}

async function getSelection(): Promise<string> {
    const tab = await getActiveTab();
    if (!tab?.id) return '';
    try {
        const [{ result }] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => window.getSelection()?.toString() || '',
        });
        return typeof result === 'string' ? result : '';
    } catch {
        return '';
    }
}

async function captureScreen(): Promise<string | null> {
    const tab = await getActiveTab();
    if (!tab?.windowId) return null;
    try {
        const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
        return dataUrl.replace('data:image/png;base64,', '');
    } catch {
        return null;
    }
}

export default function Page() {
    const [output, setOutput] = useState('');
    const [status, setStatus] = useState<{ kind: 'idle' | 'busy' | 'error'; msg: string }>({ kind: 'idle', msg: '' });

    const runStreaming = async (message: string, image?: string) => {
        setOutput('');
        setStatus({ kind: 'busy', msg: 'Thinking…' });
        try {
            await streamChat({
                message,
                mode: image ? 'vision' : 'chat',
                image,
                onChunk: (text) => setOutput((prev) => prev + text),
            });
            setStatus({ kind: 'idle', msg: '' });
        } catch (err) {
            setStatus({ kind: 'error', msg: err instanceof Error ? err.message : String(err) });
        }
    };

    const onSummarize = async () => {
        const page = await getPageText();
        if (!page) {
            setStatus({ kind: 'error', msg: 'Cannot read page (try a regular http(s) page).' });
            return;
        }
        await runStreaming(
            `Summarize this web page in 5–8 bullets. Be concrete; surface the key claims, numbers, and conclusions.\n\nURL: ${page.url}\nTitle: ${page.title}\n\n${page.text}`,
        );
    };

    const onAskAboutPage = async () => {
        const question = window.prompt('What would you like to know about this page?');
        if (!question) return;
        const page = await getPageText();
        if (!page) {
            setStatus({ kind: 'error', msg: 'Cannot read page (try a regular http(s) page).' });
            return;
        }
        await runStreaming(
            `Answer the user's question using the page below as the source. Cite specific phrases when helpful.\n\nQuestion: ${question}\n\nURL: ${page.url}\nTitle: ${page.title}\n\n${page.text}`,
        );
    };

    const onCaptureAsk = async () => {
        const question = window.prompt('What do you want to ask about the screenshot?', 'Describe what you see on this screen');
        if (!question) return;
        const image = await captureScreen();
        if (!image) {
            setStatus({ kind: 'error', msg: 'Screenshot failed.' });
            return;
        }
        await runStreaming(question, image);
    };

    const onExplainSelection = async () => {
        const selection = await getSelection();
        if (!selection.trim()) {
            setStatus({ kind: 'error', msg: 'Select some text on the page first.' });
            return;
        }
        await runStreaming(`Explain the following text clearly and concisely:\n\n${selection.slice(0, 4000)}`);
    };

    return (
        <div style={styles.container}>
            <div style={styles.actions}>
                <button style={styles.btn} onClick={onSummarize}>
                    <span style={styles.btnEmoji}>📄</span>Summarize
                </button>
                <button style={styles.btn} onClick={onAskAboutPage}>
                    <span style={styles.btnEmoji}>💬</span>Ask page
                </button>
                <button style={styles.btn} onClick={onCaptureAsk}>
                    <span style={styles.btnEmoji}>📸</span>Capture
                </button>
                <button style={styles.btn} onClick={onExplainSelection}>
                    <span style={styles.btnEmoji}>✍️</span>Explain selection
                </button>
            </div>
            {output ? (
                <div style={styles.output}>{output}</div>
            ) : (
                <div style={styles.placeholder}>
                    Pick an action. Output streams here.
                </div>
            )}
            {status.kind !== 'idle' && (
                <div style={{ ...styles.status, ...(status.kind === 'busy' ? styles.busy : styles.error) }}>
                    {status.msg}
                </div>
            )}
        </div>
    );
}
