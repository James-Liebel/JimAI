import { lazy, Suspense, useRef, useEffect, useCallback } from 'react';
import type { Message } from '../lib/types';
import { useMediaQuery } from '../hooks/useMediaQuery';

const MessageBubble = lazy(() => import('./MessageBubble'));

interface Props {
    messages: Message[];
    isStreaming: boolean;
    searchingWeb?: boolean;
    searchStatus?: string;
}

export default function ChatThread({ messages, isStreaming, searchingWeb = false, searchStatus = '' }: Props) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const isMobile = useMediaQuery('(max-width: 768px)');

    const scrollToBottom = useCallback((instant = false) => {
        requestAnimationFrame(() => {
            const el = scrollRef.current;
            if (el) {
                el.scrollTo({
                    top: el.scrollHeight,
                    behavior: instant ? 'instant' : 'smooth',
                });
            }
        });
    }, []);

    // Scroll to bottom when messages change (new message or loaded chat)
    const msgCount = messages.length;
    useEffect(() => {
        scrollToBottom(true);
    }, [msgCount, scrollToBottom]);

    // Scroll during streaming as content grows
    const lastContent = messages[messages.length - 1]?.content;
    useEffect(() => {
        if (isStreaming) scrollToBottom(false);
    }, [lastContent, isStreaming, scrollToBottom]);

    return (
        <div ref={scrollRef} className={`h-full overflow-y-auto ${isMobile ? 'px-2 py-4' : 'px-4 py-6'} space-y-3`}>
            {messages.length === 0 && (
                <div className="flex flex-col items-center justify-center h-full text-text-muted animate-fade-in px-4">
                    <div className={`rounded-xl bg-gradient-to-br from-accent-blue to-accent-purple flex items-center justify-center text-white font-bold mb-4 ${isMobile ? 'w-10 h-10 text-base' : 'w-12 h-12 text-lg'}`}>
                        AI
                    </div>
                    <h2 className={`font-semibold text-text-secondary mb-1 ${isMobile ? 'text-sm' : 'text-base'}`}>
                        jimAI
                    </h2>
                    <p className={`text-text-muted max-w-sm text-center ${isMobile ? 'text-xs' : 'text-xs'}`}>
                        {isMobile
                            ? 'Ask anything — math, code, data, images.'
                            : 'Paste anything — code, math, data, images. The system auto-routes to the right model.'}
                    </p>
                    <div className={`mt-4 grid gap-2 w-full ${isMobile ? 'grid-cols-2 max-w-sm' : 'grid-cols-2 max-w-lg mt-6'}`}>
                        {[
                            { icon: '∑', label: 'Math', desc: 'Proofs, LaTeX', color: 'text-accent-blue' },
                            { icon: '⟨/⟩', label: 'Code', desc: 'Write, fix', color: 'text-accent-green' },
                            { icon: '📊', label: 'Data', desc: 'EDA, ML', color: 'text-accent-amber' },
                            { icon: '👁', label: 'Vision', desc: 'Images, OCR', color: 'text-accent-purple' },
                        ].map((item) => (
                            <div key={item.label} className={`bg-surface-1 rounded-md border border-surface-3 ${isMobile ? 'p-2.5' : 'p-3'}`}>
                                <div className={`${item.color} font-medium flex items-center gap-1.5 mb-0.5 ${isMobile ? 'text-xs' : 'text-xs'}`}>
                                    <span>{item.icon}</span> {item.label}
                                </div>
                                <p className={`text-text-muted ${isMobile ? 'text-[11px]' : 'text-[11px]'}`}>{item.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <Suspense fallback={<div className="text-xs text-text-muted">Loading messages...</div>}>
                {messages.map((msg) => (
                    <MessageBubble key={msg.id} message={msg} />
                ))}
            </Suspense>

            {isStreaming && messages.length > 0 && messages[messages.length - 1]?.content === '' && (
                <div className="flex justify-start animate-fade-in">
                    <div className="bg-surface-1 rounded-lg px-4 py-3 border border-surface-3">
                        <div className="flex items-center gap-1.5">
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
                            <span className="ml-2 text-[11px] text-text-muted">
                                {searchingWeb ? (searchStatus || 'Searching web…') : 'Thinking...'}
                            </span>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
}
