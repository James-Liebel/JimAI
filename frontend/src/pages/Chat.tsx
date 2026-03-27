import { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { useChat } from '../hooks/useChat';
import { useUpload } from '../hooks/useUpload';
import { useMediaQuery } from '../hooks/useMediaQuery';
import ChatThread from '../components/ChatThread';
import InputBar from '../components/InputBar';
import FileUpload from '../components/FileUpload';
import AgentStatus from '../components/AgentStatus';
import SessionSidebar from '../components/SessionSidebar';
import { consumeQueuedChatPrompt } from '../lib/chatBridge';
import { cn } from '../lib/utils';
import type { SpeedMode } from '../lib/types';

interface OutletCtx {
    speedMode: SpeedMode;
    onSpeedModeChange: (mode: SpeedMode) => void;
}

export default function Chat() {
    const {
        messages,
        isStreaming,
        searchingWeb,
        searchStatus,
        sendMessage,
        newChat,
        sessionId,
        modelOverride,
        setModelOverride,
        chatList,
        loadChat,
        deleteChat,
    } = useChat();

    const { speedMode, onSpeedModeChange } = (useOutletContext<OutletCtx>() ?? {
        speedMode: 'balanced' as SpeedMode,
        onSpeedModeChange: () => {},
    });

    const { uploadFile } = useUpload(sessionId);
    const isMobile = useMediaQuery('(max-width: 768px)');
    const [showSidebar, setShowSidebar] = useState(!isMobile);
    const [showMobileDrawer, setShowMobileDrawer] = useState(false);
    const [showAgentPanel, setShowAgentPanel] = useState(false);
    const lastAssistantMessage = [...messages].reverse().find((message) => message.role === 'assistant');
    const lastSourceCount = lastAssistantMessage?.sources?.length || 0;
    const lastRouting = lastAssistantMessage?.routing;
    const lastQueryCount = Number(lastRouting?.auto_web_research_query_count || 0);
    const lastFetchedPages = Number(lastRouting?.auto_web_research_fetched_pages || 0);
    const lastDomainCount = Number(lastRouting?.auto_web_research_domain_count || 0);

    const handleFileAttach = useCallback(
        async (file: File) => {
            await uploadFile(file);
        },
        [uploadFile],
    );

    const handleNewChat = useCallback(() => {
        newChat();
        if (isMobile) setShowMobileDrawer(false);
    }, [newChat, isMobile]);

    useEffect(() => {
        const pendingPrompt = consumeQueuedChatPrompt();
        if (!pendingPrompt) return;
        sendMessage(pendingPrompt).catch(() => {});
    }, [sendMessage]);

    const isDeep = speedMode === 'deep';

    return (
        <div className={cn('h-full flex bg-surface-0 overflow-hidden', isDeep && 'ring-1 ring-inset ring-amber-500/20')}>
            {showSidebar && !isMobile && (
                <SessionSidebar
                    chats={chatList}
                    activeChatId={sessionId}
                    onSelect={loadChat}
                    onDelete={deleteChat}
                    onNew={handleNewChat}
                    onClose={() => setShowSidebar(false)}
                />
            )}

            {showMobileDrawer && isMobile && (
                <SessionSidebar
                    chats={chatList}
                    activeChatId={sessionId}
                    isMobile
                    onSelect={loadChat}
                    onDelete={deleteChat}
                    onNew={handleNewChat}
                    onClose={() => setShowMobileDrawer(false)}
                />
            )}

            <div className="flex-1 flex flex-col min-w-0 relative">
                <div className={`flex-shrink-0 flex items-center justify-between border-b border-surface-3 ${isMobile ? 'px-3 py-2' : 'px-4 py-2'}`}>
                    <div className="flex items-center gap-2">
                        {isMobile ? (
                            <>
                                <button
                                    onClick={() => setShowMobileDrawer(true)}
                                    className="p-2 rounded text-text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors"
                                    title="Chat history"
                                >
                                    <Menu size={20} />
                                </button>
                                <span className="font-semibold text-sm text-text-primary">Chat</span>
                            </>
                        ) : (
                            <>
                                {!showSidebar && (
                                    <button
                                        onClick={() => setShowSidebar(true)}
                                        className="p-1.5 rounded text-text-muted hover:text-text-secondary hover:bg-surface-2 text-xs"
                                        title="Show chat history"
                                    >
                                        ☰
                                    </button>
                                )}
                            </>
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleNewChat}
                            className={`flex items-center gap-1.5 bg-surface-2 hover:bg-surface-3 text-text-secondary rounded text-xs transition-colors border border-surface-3 ${isMobile ? 'px-3 py-2 min-h-[36px]' : 'px-2.5 py-1.5'}`}
                        >
                            + New
                        </button>
                        {!isMobile && (
                            <button
                                onClick={() => setShowAgentPanel(!showAgentPanel)}
                                className="px-2.5 py-1.5 rounded text-xs text-text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors"
                            >
                                {showAgentPanel ? 'Hide' : 'Show'} Agent Panel
                            </button>
                        )}
                    </div>
                </div>
                <div className={`flex-shrink-0 border-b border-surface-3 bg-surface-1/50 ${isMobile ? 'px-3 py-1.5' : 'px-4 py-1.5'}`}>
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <p className="text-text-secondary">
                            Auto mode: web research and browser-style lookup run in the background when your prompt needs external info.
                        </p>
                        {searchingWeb && (
                            <span className="rounded-full border border-accent-blue/30 bg-accent-blue/10 px-2 py-1 text-accent-blue">
                                {searchStatus || 'Searching web…'}
                            </span>
                        )}
                        {lastAssistantMessage && (
                            <>
                                {lastSourceCount > 0 && (
                                    <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-1 text-accent">
                                        Last answer used {lastSourceCount} source{lastSourceCount === 1 ? '' : 's'}
                                    </span>
                                )}
                                {lastRouting?.auto_web_research_attempted && (
                                    <span
                                        className={cn(
                                            'rounded-full border px-2 py-1',
                                            lastRouting.auto_web_research_ok
                                                ? 'border-accent-green/30 bg-accent-green/10 text-accent-green'
                                                : 'border-accent-amber/30 bg-accent-amber/10 text-accent-amber',
                                        )}
                                    >
                                        {lastRouting.auto_web_research_ok ? 'Web lookup confirmed' : 'Web lookup attempted'}
                                    </span>
                                )}
                                {lastQueryCount > 0 && (
                                    <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                        {lastQueryCount} search quer{lastQueryCount === 1 ? 'y' : 'ies'}
                                    </span>
                                )}
                                {lastFetchedPages > 0 && (
                                    <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                        {lastFetchedPages} page{lastFetchedPages === 1 ? '' : 's'} read
                                    </span>
                                )}
                                {lastDomainCount > 0 && (
                                    <span className="rounded-full border border-surface-4 px-2 py-1 text-text-primary">
                                        {lastDomainCount} site{lastDomainCount === 1 ? '' : 's'}
                                    </span>
                                )}
                            </>
                        )}
                    </div>
                </div>

                <div className="flex-1 flex overflow-hidden">
                    <div className="flex-1 flex flex-col min-w-0">
                        <div className="flex-1 overflow-hidden">
                            <ChatThread
                                messages={messages}
                                isStreaming={isStreaming}
                                searchingWeb={searchingWeb}
                                searchStatus={searchStatus}
                            />
                        </div>

                        <div className={`flex-shrink-0 ${isMobile ? 'px-2 pb-2 pt-1' : 'px-4 pb-3 pt-2'}`}>
                            <InputBar
                                onSend={sendMessage}
                                isStreaming={isStreaming}
                                modelOverride={modelOverride}
                                onModelOverrideChange={setModelOverride}
                                onFileAttach={handleFileAttach}
                                isMobile={isMobile}
                                speedMode={speedMode}
                                onSpeedModeChange={onSpeedModeChange}
                            />
                        </div>
                    </div>

                    {showAgentPanel && !isMobile && (
                        <AgentStatus onClose={() => setShowAgentPanel(false)} />
                    )}
                </div>
            </div>

            <FileUpload onUpload={handleFileAttach} />
        </div>
    );
}
