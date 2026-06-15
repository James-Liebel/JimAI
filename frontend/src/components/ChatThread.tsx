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
        <div ref={scrollRef} className={`h-full overflow-y-auto ${isMobile ? 'px-3 py-4' : 'px-6 py-8'}`}>
            {messages.length === 0 ? (
                <div className={`relative flex h-full flex-col items-center text-text-muted animate-fade-in px-4 ${isMobile ? 'pt-[16vh]' : 'justify-center'}`}>
                    {/* full-bleed ambient gradient backdrop */}
                    <div aria-hidden className="hero-bg" />
                    <div className="hero-orb-scene relative mb-6">
                        <div className={`hero-orb flex items-center justify-center font-bold text-white ${isMobile ? 'h-16 w-16 text-lg' : 'h-20 w-20 text-xl'}`}>
                            <span className="drop-shadow-[0_1px_4px_rgba(0,0,0,0.4)]">AI</span>
                            <div aria-hidden className="hero-orb-ring" />
                        </div>
                    </div>
                    <h2 className={`relative font-serif font-medium tracking-tight text-text-primary ${isMobile ? 'text-2xl' : 'text-3xl'}`}>
                        jimAI
                    </h2>
                    <p className={`relative mt-2 text-text-secondary ${isMobile ? 'text-sm' : 'text-base'}`}>
                        How can I help?
                    </p>
                </div>
            ) : (
                <div className={`mx-auto w-full max-w-3xl ${isMobile ? 'space-y-5' : 'space-y-6'}`}>
                    <Suspense fallback={<div className="text-xs text-text-muted">Loading messages…</div>}>
                        {messages.map((msg) => (
                            <MessageBubble key={msg.id} message={msg} />
                        ))}
                    </Suspense>

                    {isStreaming && messages[messages.length - 1]?.content === '' && (
                        <div className="flex items-center gap-1.5 py-1 animate-fade-in">
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '0ms' }} />
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '150ms' }} />
                            <div className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: '300ms' }} />
                            <span className="ml-2 text-xs text-text-muted">
                                {searchingWeb ? (searchStatus || 'Searching web…') : 'Thinking…'}
                            </span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
