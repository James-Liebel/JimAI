import { useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { v4 as uuid } from 'uuid';
import * as api from '../lib/api';
import { apiUrl } from '../lib/backendBase';

interface Cell {
    id: string;
    type: 'code' | 'markdown';
    source: string;
    output: string;
    running: boolean;
}

export default function Notebook() {
    const [cells, setCells] = useState<Cell[]>([
        { id: uuid(), type: 'code', source: '', output: '', running: false },
    ]);

    const addCell = (type: 'code' | 'markdown') => {
        setCells((prev) => [...prev, { id: uuid(), type, source: '', output: '', running: false }]);
    };

    const updateCell = useCallback((id: string, source: string) => {
        setCells((prev) => prev.map((c) => (c.id === id ? { ...c, source } : c)));
    }, []);

    const deleteCell = useCallback((id: string) => {
        setCells((prev) => prev.filter((c) => c.id !== id));
    }, []);

    const runCell = useCallback(async (id: string) => {
        setCells((prev) => prev.map((c) => (c.id === id ? { ...c, running: true, output: '' } : c)));

        const cell = cells.find((c) => c.id === id);
        if (!cell) return;

        try {
            const result = await api.executeCode(cell.source);
            const output = result.stdout + (result.stderr ? `\nStderr: ${result.stderr}` : '');
            setCells((prev) => prev.map((c) => (c.id === id ? { ...c, running: false, output } : c)));
        } catch (err) {
            setCells((prev) =>
                prev.map((c) =>
                    c.id === id ? { ...c, running: false, output: `Error: ${err}` } : c,
                ),
            );
        }
    }, [cells]);

    const askAI = useCallback(async (id: string) => {
        const cell = cells.find((c) => c.id === id);
        if (!cell) return;

        setCells((prev) => prev.map((c) => (c.id === id ? { ...c, running: true } : c)));

        try {
            const resp = await api.fetchWithTimeout(apiUrl('/api/chat'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: `Explain this code and suggest improvements:\n\n${cell.source}`,
                    mode: 'code',
                    session_id: 'notebook',
                    history: [],
                }),
            }, 120000);
            if (!resp.ok) throw new Error(`Notebook chat failed: ${resp.status}`);

            const reader = resp.body?.getReader();
            if (!reader) return;

            const decoder = new TextDecoder();
            let fullText = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const text = decoder.decode(value, { stream: true });
                const lines = text.split('\n');
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.text) fullText += data.text;
                    } catch {
                        // skip
                    }
                }
            }

            setCells((prev) =>
                prev.map((c) => (c.id === id ? { ...c, running: false, output: fullText } : c)),
            );
        } catch (err) {
            setCells((prev) =>
                prev.map((c) => (c.id === id ? { ...c, running: false, output: `Error: ${err}` } : c)),
            );
        }
    }, [cells]);

    return (
        <div className="h-full flex flex-col bg-surface-0">
            {/* Toolbar */}
            <div className="flex-shrink-0 flex items-center gap-2 px-4 py-2 border-b border-surface-3 bg-surface-1">
                <span className="text-sm font-medium text-text-secondary">📓 Notebook</span>
                <div className="flex-1" />
                <button
                    onClick={() => addCell('code')}
                    className="px-2.5 py-1 text-xs bg-surface-2 hover:bg-surface-3 text-text-secondary rounded border border-surface-3 transition-colors"
                >
                    + Code Cell
                </button>
                <button
                    onClick={() => addCell('markdown')}
                    className="px-2.5 py-1 text-xs bg-surface-2 hover:bg-surface-3 text-text-secondary rounded border border-surface-3 transition-colors"
                >
                    + Markdown Cell
                </button>
            </div>

            {/* Cells */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 max-w-5xl mx-auto w-full">
                {cells.map((cell, idx) => (
                    <div key={cell.id} className="border border-surface-3 rounded-md bg-surface-1 overflow-hidden group">
                        {/* Cell toolbar */}
                        <div className="flex items-center gap-1 px-2 py-1 bg-surface-2 border-b border-surface-3">
                            <span className="text-[10px] text-text-muted font-mono w-6">[{idx + 1}]</span>
                            <span className="text-[10px] text-text-muted">{cell.type}</span>
                            <div className="flex-1" />
                            {cell.type === 'code' && (
                                <>
                                    <button
                                        onClick={() => runCell(cell.id)}
                                        disabled={cell.running}
                                        className="px-1.5 py-0.5 text-[10px] bg-accent-green/15 text-accent-green rounded hover:bg-accent-green/25 disabled:opacity-50"
                                    >
                                        {cell.running ? '...' : '▶ Run'}
                                    </button>
                                    <button
                                        onClick={() => askAI(cell.id)}
                                        disabled={cell.running}
                                        className="px-1.5 py-0.5 text-[10px] bg-accent-blue/15 text-accent-blue rounded hover:bg-accent-blue/25 disabled:opacity-50"
                                    >
                                        Ask AI
                                    </button>
                                </>
                            )}
                            <button
                                onClick={() => deleteCell(cell.id)}
                                className="px-1.5 py-0.5 text-[10px] text-text-muted hover:text-accent-red rounded opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                                ✕
                            </button>
                        </div>

                        {/* Editor */}
                        <div className="min-h-[80px]">
                            <Editor
                                height={Math.max(80, Math.min(300, (cell.source.split('\n').length + 1) * 19))}
                                language={cell.type === 'code' ? 'python' : 'markdown'}
                                value={cell.source}
                                onChange={(v) => updateCell(cell.id, v || '')}
                                theme="vs-dark"
                                options={{
                                    minimap: { enabled: false },
                                    scrollBeyondLastLine: false,
                                    lineNumbers: 'on',
                                    fontSize: 13,
                                    fontFamily: "'JetBrains Mono', monospace",
                                    padding: { top: 8, bottom: 8 },
                                    renderLineHighlight: 'none',
                                    overviewRulerLanes: 0,
                                    hideCursorInOverviewRuler: true,
                                    scrollbar: { vertical: 'hidden' },
                                }}
                            />
                        </div>

                        {/* Output */}
                        {cell.output && (
                            <div className="border-t border-surface-3 bg-surface-0 p-3">
                                <pre className="text-xs font-mono text-text-secondary whitespace-pre-wrap max-h-60 overflow-y-auto">
                                    {cell.output}
                                </pre>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
