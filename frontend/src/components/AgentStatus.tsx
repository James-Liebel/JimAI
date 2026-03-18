import { useState, useEffect, useRef } from 'react';
import type { AgentUpdate } from '../lib/types';
import { cn } from '../lib/utils';

interface Props {
    onClose?: () => void;
}

export default function AgentStatus({ onClose }: Props) {
    const [updates, setUpdates] = useState<AgentUpdate[]>([]);
    const [isActive, setIsActive] = useState(false);
    const [elapsed, setElapsed] = useState(0);
    const timerRef = useRef<ReturnType<typeof setInterval>>();

    useEffect(() => {
        let eventSource: EventSource | null = null;

        const connect = () => {
            eventSource = new EventSource('/api/agents/status');

            eventSource.onmessage = (event) => {
                try {
                    const data: AgentUpdate = JSON.parse(event.data);
                    if (data.keepalive) return;

                    setIsActive(true);
                    setUpdates((prev) => [...prev.slice(-30), data]);

                    if (data.status === 'done' && data.final_response) {
                        setTimeout(() => setIsActive(false), 3000);
                    }
                } catch {
                    // skip
                }
            };

            eventSource.onerror = () => {
                eventSource?.close();
                setTimeout(connect, 5000);
            };
        };

        connect();
        return () => eventSource?.close();
    }, []);

    useEffect(() => {
        if (isActive) {
            setElapsed(0);
            timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
        } else {
            if (timerRef.current) clearInterval(timerRef.current);
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [isActive]);

    const currentAgent = updates[updates.length - 1];
    const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

    return (
        <div className="w-64 flex-shrink-0 border-l border-surface-3 bg-surface-1 flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b border-surface-3">
                <div className="flex items-center gap-1.5">
                    {isActive && <div className="w-1.5 h-1.5 rounded-full bg-accent-amber animate-pulse" />}
                    <span className="text-xs font-medium text-text-secondary">
                        {isActive ? 'Agent Running' : 'Agent Status'}
                    </span>
                </div>
                {onClose && (
                    <button onClick={onClose} className="text-text-muted hover:text-text-secondary text-xs p-1">✕</button>
                )}
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {isActive && currentAgent && (
                    <div className="animate-fade-in">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-medium text-text-primary">{currentAgent.agent}</span>
                            <span className="text-[10px] text-text-muted font-mono">{formatTime(elapsed)}</span>
                        </div>
                        <p className="text-[11px] text-text-secondary">{currentAgent.step}</p>
                    </div>
                )}

                {updates.length > 0 && (
                    <div className="space-y-0.5">
                        <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Step log</div>
                        {updates.map((u, i) => (
                            <div
                                key={i}
                                className={cn(
                                    'text-[11px] px-2 py-0.5 rounded font-mono',
                                    u.status === 'running' && 'text-accent-blue',
                                    u.status === 'done' && 'text-accent-green',
                                    u.status === 'error' && 'text-accent-red',
                                )}
                            >
                                {u.status === 'done' ? '✓' : u.status === 'error' ? '✗' : '●'}{' '}
                                <span className="opacity-60">[{u.agent}]</span> {u.step}
                            </div>
                        ))}
                    </div>
                )}

                {updates.length === 0 && (
                    <p className="text-[11px] text-text-muted">No agent activity yet.</p>
                )}
            </div>
        </div>
    );
}
