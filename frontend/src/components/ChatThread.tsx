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
                <div className={`relative flex flex-col items-center text-text-muted animate-fade-in px-4 ${isMobile ? 'pt-[16vh]' : 'h-full justify-center'}`}>
                    {/* aurora backdrop — decorative, sits behind the orb */}
                    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
                        <div className="hero-aurora left-1/2 top-[8%] h-44 w-72 -translate-x-[70%] bg-accent-blue" />
                        <div className="hero-aurora left-1/2 top-[14%] h-40 w-64 -translate-x-[20%] bg-accent-purple [animation-delay:-8s]" />
                    </div>
                    <div className="hero-orb-scene relative mb-5">
                        <div className={`hero-orb flex items-center justify-center font-bold text-white ${isMobile ? 'h-16 w-16 text-lg' : 'h-20 w-20 text-xl'}`}>
                            <span className="drop-shadow-[0_1px_4px_rgba(0,0,0,0.4)]">AI</span>
                            <div aria-hidden className="hero-orb-ring" />
                        </div>
                    </div>
                    <h2 className={`relative font-semibold text-text-secondary ${isMobile ? 'text-base' : 'text-lg'}`}>
                        jimAI
                    </h2>
                    <p className={`relative mt-1 text-text-muted ${isMobile ? 'text-xs' : 'text-sm'}`}>
                        How can I help?
                    </p>
                </div>
            )}

            <Suspense fallback={<div className="text-xs text-text-muted">Loading messages...</div>}>
                {messages.map((msg) => (
                    <MessageBubble key={msg.id} message={msg} />
                ))}
            </Suspense>

            {isStreaming && messages.length > 0 && messages[messages.length - 1]?.content === '' && (
                <div className="flex justify-start animate-fade-in">
                    <div className="bg-surface-1 rounded-panel px-4 py-3 border border-surface-4 shadow-elevation-1">
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
