import React, { useCallback, useEffect, useRef, useState } from 'react';
import { streamChat } from './lib/api';
import { loadHistory, saveHistory, StoredMessage } from './lib/storage';

const HISTORY_FOR_MODEL = 12;

export default function Chat() {
    const [messages, setMessages] = useState<StoredMessage[]>([]);
    const [input, setInput] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [capturedImage, setCapturedImage] = useState<string | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        loadHistory().then(setMessages).catch(() => {});
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isStreaming]);

    useEffect(() => {
        if (messages.length === 0) return;
        const id = window.setTimeout(() => { void saveHistory(messages); }, 400);
        return () => window.clearTimeout(id);
    }, [messages]);

    useEffect(() => {
        const handler = (msg: { type: string; image?: string }) => {
            if (msg.type === 'SCREENSHOT_CAPTURED' && msg.image) {
                setCapturedImage(msg.image);
                setInput('Describe what you see on this screen');
            }
        };
        chrome.runtime.onMessage.addListener(handler);
        return () => chrome.runtime.onMessage.removeListener(handler);
    }, []);

    const sendMessage = useCallback(async () => {
        const text = input.trim();
        if (!text || isStreaming) return;

        const userMsg: StoredMessage = { role: 'user', content: text, timestamp: Date.now() };
        const placeholder: StoredMessage = { role: 'assistant', content: '', timestamp: Date.now() };
        setMessages((prev) => [...prev, userMsg, placeholder]);
        setInput('');
        setIsStreaming(true);

        const historyForModel = messages
            .slice(-HISTORY_FOR_MODEL)
            .map((m) => ({ role: m.role, content: m.content }));

        const controller = new AbortController();
        abortRef.current = controller;
        const image = capturedImage;
        if (image) setCapturedImage(null);

        try {
            await streamChat({
                message: text,
                mode: image ? 'vision' : 'chat',
                history: historyForModel,
                image: image || undefined,
                signal: controller.signal,
                onChunk: (chunk) => {
                    setMessages((prev) => {
                        const updated = [...prev];
                        const last = updated[updated.length - 1];
                        if (last && last.role === 'assistant') {
                            updated[updated.length - 1] = { ...last, content: last.content + chunk };
                        }
                        return updated;
                    });
                },
            });
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = {
                        ...last,
                        content: last.content || `Error: ${msg}`,
                    };
                }
                return updated;
            });
        } finally {
            setIsStreaming(false);
            abortRef.current = null;
        }
    }, [input, isStreaming, messages, capturedImage]);

    const stop = () => {
        abortRef.current?.abort();
        abortRef.current = null;
        setIsStreaming(false);
    };

    return (
        <div style={styles.container}>
            {capturedImage && (
                <div style={styles.imagePreview}>
                    <img src={`data:image/png;base64,${capturedImage}`} alt="Captured" style={styles.previewImg} />
                    <button onClick={() => setCapturedImage(null)} style={styles.removeBtn}>×</button>
                </div>
            )}

            <div style={styles.messages}>
                {messages.length === 0 && (
                    <div style={styles.placeholder}>
                        Ask anything. Use the Page tab for tools that work on the current website.
                    </div>
                )}
                {messages.map((msg, i) => (
                    <div
                        key={i}
                        style={{
                            ...styles.msg,
                            ...(msg.role === 'user' ? styles.userMsg : styles.assistantMsg),
                        }}
                    >
                        {msg.content || (isStreaming && i === messages.length - 1 ? '…' : '')}
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>

            <div style={styles.inputArea}>
                <textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            void sendMessage();
                        }
                    }}
                    placeholder="Message JimAI…"
                    style={styles.input}
                    rows={2}
                    disabled={isStreaming}
                />
                {isStreaming ? (
                    <button onClick={stop} style={styles.stopBtn} title="Stop">■</button>
                ) : (
                    <button onClick={sendMessage} disabled={!input.trim()} style={styles.sendBtn} title="Send (Enter)">↑</button>
                )}
            </div>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    container: { height: '100%', display: 'flex', flexDirection: 'column', color: '#e8e8f0', background: '#0a0a0c' },
    imagePreview: { padding: '8px 12px', position: 'relative', borderBottom: '1px solid #1e1e24' },
    previewImg: { width: '100%', borderRadius: '4px', maxHeight: '100px', objectFit: 'cover' },
    removeBtn: {
        position: 'absolute', top: '12px', right: '16px', background: '#1e1e24',
        border: 'none', color: '#e8e8f0', borderRadius: '50%',
        width: '20px', height: '20px', cursor: 'pointer', fontSize: '12px',
    },
    placeholder: { color: '#55556A', fontSize: '12px', textAlign: 'center', padding: '32px 16px' },
    messages: { flex: 1, overflow: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '6px' },
    msg: { padding: '8px 10px', borderRadius: '8px', fontSize: '12px', lineHeight: '1.5', whiteSpace: 'pre-wrap', maxWidth: '85%' },
    userMsg: { background: '#3B82F6', color: 'white', alignSelf: 'flex-end' },
    assistantMsg: { background: '#111114', border: '1px solid #1e1e24', color: '#e8e8f0', alignSelf: 'flex-start' },
    inputArea: { padding: '8px 12px', borderTop: '1px solid #1e1e24', display: 'flex', gap: '6px', alignItems: 'flex-end' },
    input: {
        flex: 1, background: '#111114', border: '1px solid #1e1e24', color: '#e8e8f0',
        borderRadius: '6px', padding: '8px 10px', fontSize: '12px', outline: 'none',
        resize: 'none', fontFamily: 'inherit',
    },
    sendBtn: {
        padding: '8px 12px', background: '#3B82F6', border: 'none',
        color: 'white', borderRadius: '6px', cursor: 'pointer',
        fontSize: '13px', fontWeight: 600, height: '34px',
    },
    stopBtn: {
        padding: '8px 12px', background: 'transparent', border: '1px solid #EF4444',
        color: '#EF4444', borderRadius: '6px', cursor: 'pointer',
        fontSize: '11px', height: '34px',
    },
};
