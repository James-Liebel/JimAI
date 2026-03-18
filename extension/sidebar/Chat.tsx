import React, { useState, useCallback, useEffect, useRef } from 'react';

const BACKEND = 'http://localhost:8000';

interface Message {
    role: 'user' | 'assistant';
    content: string;
}

export default function Chat() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isStreaming, setIsStreaming] = useState(false);
    const [capturedImage, setCapturedImage] = useState<string | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        const handler = (msg: { type: string; text?: string; mode?: string; image?: string }) => {
            if (msg.type === 'AI_RESPONSE' && msg.text) {
                setMessages(prev => [...prev, { role: 'assistant', content: msg.text! }]);
            }
            if (msg.type === 'SCREENSHOT_CAPTURED' && msg.image) {
                setCapturedImage(msg.image);
                setInput('Describe what you see on this screen');
            }
        };
        chrome.runtime.onMessage.addListener(handler);
        return () => chrome.runtime.onMessage.removeListener(handler);
    }, []);

    const sendMessage = useCallback(async () => {
        if (!input.trim() || isStreaming) return;

        const userMsg = input.trim();
        setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
        setInput('');
        setIsStreaming(true);
        setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

        try {
            if (capturedImage) {
                // Send to vision API
                const resp = await fetch(`${BACKEND}/api/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: userMsg,
                        mode: 'vision',
                        session_id: 'extension',
                        history: [],
                        image: capturedImage,
                        has_image: true,
                    }),
                });

                setCapturedImage(null);
                await streamResponse(resp);
            } else {
                const resp = await fetch(`${BACKEND}/api/chat`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: userMsg,
                        mode: 'chat',
                        session_id: 'extension',
                        history: [],
                    }),
                });
                await streamResponse(resp);
            }
        } catch (err) {
            setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last) updated[updated.length - 1] = { ...last, content: `Error: ${err}` };
                return updated;
            });
        } finally {
            setIsStreaming(false);
        }
    }, [input, isStreaming, capturedImage]);

    const streamResponse = async (resp: Response) => {
        const reader = resp.body?.getReader();
        if (!reader) return;

        const decoder = new TextDecoder();
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value, { stream: true });
            for (const line of text.split('\n')) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) {
                        setMessages(prev => {
                            const updated = [...prev];
                            const last = updated[updated.length - 1];
                            if (last) updated[updated.length - 1] = { ...last, content: last.content + data.text };
                            return updated;
                        });
                    }
                } catch { /* skip */ }
            }
        }
    };

    const captureScreen = async () => {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab?.id && tab.windowId) {
            try {
                const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
                const base64 = screenshot.replace('data:image/png;base64,', '');
                setCapturedImage(base64);
                setInput('Describe what you see on this screen');
            } catch (e) {
                setMessages(prev => [...prev, { role: 'assistant', content: `Screenshot failed: ${e}` }]);
            }
        }
    };

    const readPage = async () => {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab?.id) {
            chrome.tabs.sendMessage(tab.id, { type: 'CAPTURE_REQUEST' }, async (response: { text: string }) => {
                if (response?.text) {
                    try {
                        await fetch(`${BACKEND}/api/upload/url`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ url: tab.url || 'page', session_id: 'extension' }),
                        });
                        setMessages(prev => [...prev, { role: 'assistant', content: '📄 Page content indexed! You can now ask questions about it.' }]);
                    } catch (err) {
                        setMessages(prev => [...prev, { role: 'assistant', content: `Failed to index page: ${err}` }]);
                    }
                }
            });
        }
    };

    const indexPage = async () => {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab?.url) {
            setMessages(prev => [...prev, { role: 'assistant', content: `📚 Indexing ${tab.url}...` }]);
            chrome.runtime.sendMessage({ type: 'INDEX_PAGE', url: tab.url }, (result: { success: boolean }) => {
                if (result?.success) {
                    setMessages(prev => [...prev, { role: 'assistant', content: '✓ Page permanently indexed to knowledge base.' }]);
                }
            });
        }
    };

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <span style={styles.headerTitle}>Private AI</span>
                <div style={styles.headerButtons}>
                    <button onClick={captureScreen} style={styles.headerBtn} title="Capture Screen (Alt+S)">📸</button>
                    <button onClick={readPage} style={styles.headerBtn} title="Read Page">📖</button>
                    <button onClick={indexPage} style={styles.headerBtn} title="Index Page">📚</button>
                </div>
            </div>

            {capturedImage && (
                <div style={styles.imagePreview}>
                    <img src={`data:image/png;base64,${capturedImage}`} alt="Captured" style={styles.previewImg} />
                    <button onClick={() => setCapturedImage(null)} style={styles.removeBtn}>×</button>
                </div>
            )}

            <div style={styles.messages}>
                {messages.map((msg, i) => (
                    <div key={i} style={{ ...styles.msg, ...(msg.role === 'user' ? styles.userMsg : styles.assistantMsg) }}>
                        {msg.content}
                    </div>
                ))}
                <div ref={bottomRef} />
            </div>

            <div style={styles.inputArea}>
                <input
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && sendMessage()}
                    placeholder="Message Private AI..."
                    style={styles.input}
                />
                <button onClick={sendMessage} disabled={isStreaming} style={{ ...styles.sendBtn, opacity: isStreaming ? 0.5 : 1 }}>
                    ↑
                </button>
            </div>
        </div>
    );
}

const styles: Record<string, React.CSSProperties> = {
    container: { height: '100vh', display: 'flex', flexDirection: 'column', fontFamily: "'Inter', system-ui, sans-serif", color: '#e8e8f0', background: '#0a0a0c' },
    header: { padding: '8px 12px', borderBottom: '1px solid #1e1e24', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
    headerTitle: { fontWeight: 600, fontSize: '13px' },
    headerButtons: { display: 'flex', gap: '4px' },
    headerBtn: { fontSize: '12px', padding: '4px 6px', background: '#111114', border: '1px solid #1e1e24', color: '#7070a0', borderRadius: '4px', cursor: 'pointer' },
    imagePreview: { padding: '8px 12px', position: 'relative' as const, borderBottom: '1px solid #1e1e24' },
    previewImg: { width: '100%', borderRadius: '4px', maxHeight: '100px', objectFit: 'cover' as const },
    removeBtn: { position: 'absolute' as const, top: '12px', right: '16px', background: '#1e1e24', border: 'none', color: '#7070a0', borderRadius: '50%', width: '20px', height: '20px', cursor: 'pointer', fontSize: '12px' },
    messages: { flex: 1, overflow: 'auto', padding: '12px' },
    msg: { marginBottom: '6px', padding: '8px 10px', borderRadius: '8px', fontSize: '12px', lineHeight: '1.5', whiteSpace: 'pre-wrap' as const },
    userMsg: { background: '#4f8ef7', marginLeft: '20%' },
    assistantMsg: { background: '#111114', border: '1px solid #1e1e24', marginRight: '10%' },
    inputArea: { padding: '8px 12px', borderTop: '1px solid #1e1e24', display: 'flex', gap: '6px' },
    input: { flex: 1, background: '#111114', border: '1px solid #1e1e24', color: '#e8e8f0', borderRadius: '6px', padding: '8px 10px', fontSize: '12px', outline: 'none' },
    sendBtn: { padding: '8px 12px', background: '#4f8ef7', border: 'none', color: 'white', borderRadius: '6px', cursor: 'pointer', fontSize: '13px', fontWeight: 600 },
};
