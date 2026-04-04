import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Trash2, X, Plus, Search } from 'lucide-react';
import type { ChatListItem } from '../lib/api';
import { cn } from '../lib/utils';

interface Props {
    chats: ChatListItem[];
    activeChatId: string;
    isMobile?: boolean;
    onSelect: (chatId: string) => void;
    onDelete: (chatId: string) => void;
    onNew: () => void;
    onClose: () => void;
}

export default function SessionSidebar({
    chats,
    activeChatId,
    isMobile = false,
    onSelect,
    onDelete,
    onNew,
    onClose,
}: Props) {
    const [searchInput, setSearchInput] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const handleSearchChange = (value: string) => {
        setSearchInput(value);
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => setSearchQuery(value), 200);
    };

    useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

    const filteredChats = searchQuery.trim()
        ? chats.filter((c) => {
              const q = searchQuery.toLowerCase();
              return c.title?.toLowerCase().includes(q) || c.preview?.toLowerCase().includes(q);
          })
        : chats;

    const formatDate = (ts: number) => {
        const d = new Date(ts * 1000);
        const now = new Date();
        const diff = now.getTime() - d.getTime();
        const days = Math.floor(diff / 86400000);
        if (days === 0) return 'Today';
        if (days === 1) return 'Yesterday';
        if (days < 7) return `${days}d ago`;
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    };

    return (
        <div className={cn(
            'flex h-full flex-col border-surface-4 bg-surface-1',
            isMobile
                ? 'fixed inset-0 z-50 w-full animate-fade-in'
                : 'w-72 shrink-0 border-r',
        )}>
            {/* Header */}
            <div className={cn(
                'flex items-center justify-between border-b border-surface-4',
                isMobile ? 'px-4 py-3' : 'px-3 py-2',
            )}>
                <span className={cn(
                    'font-medium text-text-secondary',
                    isMobile ? 'text-base' : 'text-xs',
                )}>
                    Chats
                </span>
                <div className="flex items-center gap-1">
                    <button
                        type="button"
                        onClick={onNew}
                        className={cn(
                            'text-text-muted transition-colors hover:bg-surface-2 hover:text-accent',
                            isMobile ? 'p-2.5' : 'p-1.5',
                        )}
                        title="New chat"
                    >
                        <Plus size={isMobile ? 20 : 14} />
                    </button>
                    <button
                        type="button"
                        onClick={onClose}
                        className={cn(
                            'text-text-muted transition-colors hover:bg-surface-2 hover:text-text-secondary',
                            isMobile ? 'p-2.5' : 'p-1.5',
                        )}
                    >
                        <X size={isMobile ? 20 : 14} />
                    </button>
                </div>
            </div>

            {/* Search input */}
            <div className={cn('border-b border-surface-4', isMobile ? 'px-4 py-2' : 'px-3 py-1.5')}>
                <div className="flex items-center gap-1.5 border border-surface-4 bg-surface-0 px-2 py-1">
                    <Search size={isMobile ? 14 : 12} className="text-text-muted flex-shrink-0" />
                    <input
                        type="text"
                        value={searchInput}
                        onChange={(e) => handleSearchChange(e.target.value)}
                        placeholder="Search chats..."
                        className={cn(
                            'flex-1 bg-transparent text-text-primary placeholder:text-text-muted outline-none',
                            isMobile ? 'text-sm' : 'text-xs',
                        )}
                    />
                    {searchInput && (
                        <button
                            type="button"
                            onClick={() => { setSearchInput(''); setSearchQuery(''); }}
                            className="text-text-muted hover:text-text-secondary"
                        >
                            <X size={10} />
                        </button>
                    )}
                </div>
            </div>

            {/* Chat list */}
            <div className="flex-1 overflow-y-auto">
                {chats.length === 0 ? (
                    <div className={cn(
                        'text-text-muted text-center py-8',
                        isMobile ? 'text-sm' : 'text-xs',
                    )}>
                        No saved chats yet.
                        <br />Start a conversation!
                    </div>
                ) : filteredChats.length === 0 ? (
                    <div className={cn(
                        'text-text-muted text-center py-8',
                        isMobile ? 'text-sm' : 'text-xs',
                    )}>
                        No sessions match your search.
                    </div>
                ) : (
                    <div className="py-1">
                        {filteredChats.map((chat) => (
                            <div
                                key={chat.id}
                                onClick={() => {
                                    onSelect(chat.id);
                                    if (isMobile) onClose();
                                }}
                                className={cn(
                                    'group flex items-start gap-2.5 cursor-pointer transition-colors',
                                    isMobile ? 'px-4 py-3' : 'px-3 py-2',
                                    chat.id === activeChatId
                                        ? 'bg-accent/10 border-l-2 border-accent'
                                        : 'hover:bg-surface-2 border-l-2 border-transparent',
                                )}
                            >
                                <MessageSquare
                                    size={isMobile ? 18 : 14}
                                    className="text-text-muted flex-shrink-0 mt-0.5"
                                />
                                <div className="flex-1 min-w-0">
                                    <div className={cn(
                                        'text-text-primary truncate font-medium',
                                        isMobile ? 'text-sm' : 'text-xs',
                                    )}>
                                        {chat.title}
                                    </div>
                                    <div className={cn(
                                        'text-text-muted truncate mt-0.5',
                                        isMobile ? 'text-xs' : 'text-[11px]',
                                    )}>
                                        {chat.preview || 'Empty chat'}
                                    </div>
                                    <div className={cn(
                                        'text-text-muted mt-0.5',
                                        isMobile ? 'text-[11px]' : 'text-[10px]',
                                    )}>
                                        {formatDate(chat.updated_at)} · {chat.message_count} msgs
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onDelete(chat.id);
                                    }}
                                    className={cn(
                                        'shrink-0 text-text-muted transition-colors hover:bg-surface-2 hover:text-accent-red',
                                        isMobile
                                            ? 'p-2 opacity-100'
                                            : 'p-1 opacity-0 group-hover:opacity-100',
                                    )}
                                    title="Delete chat"
                                >
                                    <Trash2 size={isMobile ? 16 : 12} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
