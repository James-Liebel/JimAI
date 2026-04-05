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
import { detectLikelySystemTask } from '../lib/detectSystemIntent';
import { consumeSystemTask } from '../lib/systemTaskBridge';
import { runLocalSystemAgentAuto } from '../lib/localSystemAgentSidecar';
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

    const [localPcLog, setLocalPcLog] = useState('');
    const [localPcRunning, setLocalPcRunning] = useState(false);

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
        setLocalPcLog('');
        setLocalPcRunning(false);
        if (isMobile) setShowMobileDrawer(false);
    }, [newChat, isMobile]);

    const runLocalPcFollowUp = useCallback(async (task: string) => {
        setLocalPcRunning(true);
        setLocalPcLog('');
        try {
            await runLocalSystemAgentAuto(task, (chunk) => {
                setLocalPcLog((prev) => prev + chunk);
            });
        } catch (err) {
            setLocalPcLog((prev) => `${prev}\n**Error:** ${err instanceof Error ? err.message : String(err)}\n`);
        } finally {
            setLocalPcRunning(false);
        }
    }, []);

    const handleSend = useCallback(
        async (content: string, imageBase64?: string) => {
            await sendMessage(content, imageBase64);
            if (!imageBase64 && detectLikelySystemTask(content)) {
                void runLocalPcFollowUp(content.trim());
            }
        },
        [runLocalPcFollowUp, sendMessage],
    );

    useEffect(() => {
        const fromChat = consumeQueuedChatPrompt();
        const fromSystem = consumeSystemTask();
        const pending = fromChat || fromSystem;
        if (!pending) return;
        void (async () => {
            try {
                await sendMessage(pending);
                if (detectLikelySystemTask(pending)) {
                    await runLocalPcFollowUp(pending.trim());
                }
            } catch {
                // sendMessage surfaces errors in-thread
            }
        })();
    }, [runLocalPcFollowUp, sendMessage]);

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
                <div className={cn(
                    'flex shrink-0 items-center justify-between border-b border-surface-5 bg-surface-1',
                    isMobile ? 'px-3 py-2' : 'px-4 py-2.5',
                )}>
                    <div className="flex items-center gap-2">
                        {isMobile ? (
                            <>
                                <button
                                    onClick={() => setShowMobileDrawer(true)}
                                    className="rounded p-1.5 text-text-muted transition-colors hover:bg-surface-3 hover:text-text-secondary"
                                    title="Chat history"
                                >
                                    <Menu size={18} />
                                </button>
                                <span className="text-sm font-semibold text-text-primary">Chat</span>
                            </>
                        ) : (
                            <>
                                {!showSidebar && (
                                    <button
                                        onClick={() => setShowSidebar(true)}
                                        className="rounded p-1.5 text-text-muted transition-colors hover:bg-surface-3 hover:text-text-secondary"
                                        title="Show chat history"
                                    >
                                        <Menu size={16} />
                                    </button>
                                )}
                            </>
                        )}
                    </div>
                    <div className="flex items-center gap-1.5">
                        <button
                            onClick={handleNewChat}
                            className={cn(
                                'rounded-btn border border-surface-4 text-xs font-medium text-text-secondary transition-colors hover:border-surface-3 hover:bg-surface-3 hover:text-text-primary',
                                isMobile ? 'min-h-[34px] px-3 py-1.5' : 'px-2.5 py-1.5',
                            )}
                        >
                            + New
                        </button>
                        {!isMobile && (
                            <button
                                onClick={() => setShowAgentPanel(!showAgentPanel)}
                                className={cn(
                                    'rounded-btn px-2.5 py-1.5 text-xs font-medium transition-colors',
                                    showAgentPanel
                                        ? 'bg-accent/10 text-accent'
                                        : 'text-text-muted hover:bg-surface-3 hover:text-text-secondary',
                                )}
                            >
                                Agent Panel
                            </button>
                        )}
                    </div>
                </div>

                {/* Auto-mode info strip */}
                <div className={cn(
                    'flex-shrink-0 border-b border-surface-5 bg-surface-0/60',
                    isMobile ? 'px-3 py-1.5' : 'px-4 py-1.5',
                )}>
                    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                        <span className="text-text-muted tracking-wide">
                            Auto mode
                        </span>
                        <span className="text-surface-4">·</span>
                        <span className="text-text-muted">web research runs automatically when needed</span>
                        {searchingWeb && (
                            <span className="rounded-badge border border-accent/30 bg-accent/10 px-2 py-0.5 font-medium text-accent">
                                {searchStatus || 'Searching web…'}
                            </span>
                        )}
                        {lastAssistantMessage && (
                            <>
                                {lastSourceCount > 0 && (
                                    <span className="rounded-badge border border-accent/25 bg-accent/8 px-2 py-0.5 text-accent">
                                        {lastSourceCount} source{lastSourceCount === 1 ? '' : 's'}
                                    </span>
                                )}
                                {lastRouting?.auto_web_research_attempted && (
                                    <span
                                        className={cn(
                                            'rounded-badge border px-2 py-0.5',
                                            lastRouting.auto_web_research_ok
                                                ? 'border-accent-green/25 bg-accent-green/8 text-accent-green'
                                                : 'border-accent-amber/25 bg-accent-amber/8 text-accent-amber',
                                        )}
                                    >
                                        {lastRouting.auto_web_research_ok ? 'Web ✓' : 'Web attempted'}
                                    </span>
                                )}
                                {lastQueryCount > 0 && (
                                    <span className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-0.5 text-text-secondary">
                                        {lastQueryCount} quer{lastQueryCount === 1 ? 'y' : 'ies'}
                                    </span>
                                )}
                                {lastFetchedPages > 0 && (
                                    <span className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-0.5 text-text-secondary">
                                        {lastFetchedPages} page{lastFetchedPages === 1 ? '' : 's'}
                                    </span>
                                )}
                                {lastDomainCount > 0 && (
                                    <span className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-0.5 text-text-secondary">
                                        {lastDomainCount} site{lastDomainCount === 1 ? '' : 's'}
                                    </span>
                                )}
                                {typeof lastRouting?.context_window_messages === 'number' && (
                                    <span
                                        className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-0.5 font-mono text-text-secondary"
                                        title="Messages from this chat passed into the model for this reply (after windowing)"
                                    >
                                        ctx {lastRouting.context_window_messages} msg
                                        {typeof lastRouting.context_window_chars === 'number'
                                            ? ` · ${Math.round(lastRouting.context_window_chars / 1000)}k chars`
                                            : ''}
                                    </span>
                                )}
                                {lastRouting?.cross_chat_memory_active && (
                                    <span
                                        className="rounded-badge border border-accent/25 bg-accent/8 px-2 py-0.5 text-accent"
                                        title="Cross-chat memory bullets were included in the system prompt"
                                    >
                                        shared memory
                                    </span>
                                )}
                                {lastRouting?.rolling_summary_active && (
                                    <span
                                        className="rounded-badge border border-surface-4 bg-surface-2 px-2 py-0.5 text-text-secondary"
                                        title="Older turns in this chat were compressed into a rolling summary"
                                    >
                                        chat summary
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

                        {(localPcRunning || localPcLog.trim()) && (
                            <div className="flex-shrink-0 max-h-36 overflow-auto border-t border-surface-5 bg-surface-0 px-4 py-2">
                                <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted">
                                    Local PC · filesystem agent
                                </p>
                                <pre className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-text-secondary">
                                    {localPcRunning && !localPcLog ? 'Running local filesystem agent…' : localPcLog}
                                </pre>
                            </div>
                        )}

                        <div className={`flex-shrink-0 ${isMobile ? 'px-2 pb-2 pt-1' : 'px-4 pb-3 pt-2'}`}>
                            <InputBar
                                onSend={handleSend}
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
