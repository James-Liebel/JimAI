import { useState, useCallback, useRef, useEffect } from 'react';
import { v4 as uuid } from 'uuid';
import type { Message, Mode, Source, RoutingDecision } from '../lib/types';
import * as api from '../lib/api';

const SAVE_DEBOUNCE_MS = 2000;

export function useChat() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [searchingWeb, setSearchingWeb] = useState(false);
    const [searchStatus, setSearchStatus] = useState('');
    const [modelOverride, setModelOverride] = useState<string>('');
    const [chatId, setChatId] = useState(uuid());
    const [chatTitle, setChatTitle] = useState('');
    const [chatList, setChatList] = useState<api.ChatListItem[]>([]);
    const sessionIdRef = useRef(chatId);
    const saveTimerRef = useRef<ReturnType<typeof setTimeout>>();

    useEffect(() => {
        sessionIdRef.current = chatId;
    }, [chatId]);

    const refreshChatList = useCallback(async () => {
        const list = await api.listChats();
        setChatList(list);
    }, []);

    useEffect(() => {
        refreshChatList();
    }, [refreshChatList]);

    const autoSave = useCallback((msgs: Message[], id: string, title: string) => {
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = setTimeout(async () => {
            if (msgs.length === 0) return;
            const serializable = msgs.map((m) => {
                let content = m.content;
                if (m.browserScreenshotUrl) {
                    const note = `_(Page captured: ${m.browserScreenshotUrl})_`;
                    content = content.trim() ? `${content.trim()}\n\n${note}` : note;
                }
                return {
                    id: m.id,
                    role: m.role,
                    content,
                    mode: m.mode,
                    timestamp: m.timestamp,
                };
            });
            const autoTitle = title || deriveTitle(msgs);
            await api.saveChat(id, autoTitle, serializable);
            refreshChatList();
        }, SAVE_DEBOUNCE_MS);
    }, [refreshChatList]);

    const sendMessage = useCallback(
        async (content: string, imageBase64?: string) => {
            const mode: Mode = modelOverride ? (modelOverride as Mode) : 'chat';

            const userMsg: Message = {
                id: uuid(),
                role: 'user',
                content,
                mode,
                timestamp: Date.now(),
                imageBase64,
            };

            const assistantMsg: Message = {
                id: uuid(),
                role: 'assistant',
                content: '',
                mode,
                timestamp: Date.now(),
                isStreaming: true,
            };

            setMessages((prev) => [...prev, userMsg, assistantMsg]);
            setIsStreaming(true);
            setSearchingWeb(false);
            setSearchStatus('');

            const appendChunk = (text: string) => {
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === 'assistant') {
                        updated[updated.length - 1] = {
                            ...last,
                            content: last.content + text,
                        };
                    }
                    return updated;
                });
            };

            const setSources = (sources: Source[]) => {
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === 'assistant') {
                        updated[updated.length - 1] = { ...last, sources };
                    }
                    return updated;
                });
            };

            const setRouting = (routing: RoutingDecision) => {
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === 'assistant') {
                        const role = routing.primary_role || routing.primary_model;
                        updated[updated.length - 1] = {
                            ...last,
                            routing,
                            mode: (role as Mode) || last.mode,
                        };
                    }
                    return updated;
                });
            };

            const currentChatId = sessionIdRef.current;
            const currentTitle = chatTitle;

            const onDone = () => {
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === 'assistant') {
                        updated[updated.length - 1] = { ...last, isStreaming: false };
                    }
                    autoSave(updated, currentChatId, currentTitle);
                    return updated;
                });
                setIsStreaming(false);
                setSearchingWeb(false);
                setSearchStatus('');
            };

            try {
                const history = messages.map((m) => ({
                    role: m.role,
                    content: m.content,
                }));
                const apiMode = 'chat';
                await api.streamChat(
                    content,
                    apiMode,
                    sessionIdRef.current,
                    history,
                    appendChunk,
                    setSources,
                    setRouting,
                    onDone,
                    (progress) => {
                        if (typeof progress.searchingWeb === 'boolean') setSearchingWeb(progress.searchingWeb);
                        if (typeof progress.searchStatus === 'string') setSearchStatus(progress.searchStatus);
                        if (progress.browserScreenshotB64) {
                            setMessages((prev) => {
                                const updated = [...prev];
                                const last = updated[updated.length - 1];
                                if (last && last.role === 'assistant') {
                                    updated[updated.length - 1] = {
                                        ...last,
                                        browserScreenshotBase64: progress.browserScreenshotB64,
                                        browserScreenshotUrl: progress.browserScreenshotUrl,
                                    };
                                }
                                return updated;
                            });
                        }
                    },
                    modelOverride || undefined,
                    imageBase64,
                    undefined,
                    true,
                );
            } catch (err) {
                appendChunk(`\n\n**Error:** ${err instanceof Error ? err.message : 'Unknown error'}`);
                setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last?.role === 'assistant' && last.isStreaming) {
                        updated[updated.length - 1] = { ...last, isStreaming: false };
                    }
                    return updated;
                });
                setIsStreaming(false);
                setSearchingWeb(false);
                setSearchStatus('');
            }
        },
        [messages, modelOverride, chatTitle, autoSave],
    );

    const newChat = useCallback(async () => {
        await api.clearHistory(sessionIdRef.current);
        const newId = uuid();
        setChatId(newId);
        setChatTitle('');
        setMessages([]);
    }, []);

    const loadChatById = useCallback(async (id: string) => {
        const data = await api.loadChat(id);
        if (!data) return;
        setChatId(data.id);
        setChatTitle(data.title);
        const loaded: Message[] = data.messages.map((m: any) => ({
            id: m.id || uuid(),
            role: m.role,
            content: m.content,
            mode: m.mode || 'chat',
            timestamp: m.timestamp || Date.now(),
            isStreaming: false,
        }));
        setMessages(loaded);
    }, []);

    const deleteChatById = useCallback(async (id: string) => {
        await api.deleteChat(id);
        if (id === chatId) {
            newChat();
        }
        refreshChatList();
    }, [chatId, newChat, refreshChatList]);

    return {
        messages,
        isStreaming,
        searchingWeb,
        searchStatus,
        modelOverride,
        setModelOverride,
        sendMessage,
        newChat,
        sessionId: chatId,
        chatList,
        loadChat: loadChatById,
        deleteChat: deleteChatById,
        refreshChatList,
    };
}

function deriveTitle(messages: Message[]): string {
    for (const msg of messages) {
        if (msg.role === 'user' && msg.content) {
            const text = msg.content.trim();
            if (text.length <= 40) return text;
            return text.slice(0, 37) + '...';
        }
    }
    return 'New chat';
}
