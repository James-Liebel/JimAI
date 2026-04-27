import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    MessageSquare, Globe, Hammer, Bot, Wrench, GitPullRequest, Sparkles,
    Settings as SettingsIcon, LayoutDashboard, FlaskConical, Search, FileText, ListChecks,
    type LucideIcon,
} from 'lucide-react';
import { cn } from '../lib/utils';

interface PaletteItem {
    id: string;
    label: string;
    hint?: string;
    icon: LucideIcon;
    to: string;
    keywords?: string;
}

const ITEMS: PaletteItem[] = [
    { id: 'chat',     label: 'Chat',          icon: MessageSquare,    to: '/chat',         keywords: 'message ask question' },
    { id: 'atlas',    label: 'Atlas Browser', icon: Globe,            to: '/atlas',        keywords: 'web browse internet' },
    { id: 'builder',  label: 'Builder',       icon: Hammer,           to: '/builder',      keywords: 'build agent run' },
    { id: 'agents',   label: 'Agents',        icon: Bot,              to: '/agents',       keywords: 'team workspace persona' },
    { id: 'self',     label: 'SelfCode',      icon: Wrench,           to: '/self-code',    keywords: 'edit codebase repo' },
    { id: 'review',   label: 'JimAI Review',  icon: GitPullRequest,   to: '/workflow',     keywords: 'pr pull request workflow' },
    { id: 'skills',   label: 'Skills',        icon: Sparkles,         to: '/skills',       keywords: 'capabilities' },
    { id: 'research', label: 'Research',      icon: Search,           to: '/research',     keywords: 'search papers web' },
    { id: 'audit',    label: 'System Audit',  icon: FlaskConical,     to: '/audit',        keywords: 'health diagnostics' },
    { id: 'auto',     label: 'Automation',    icon: ListChecks,       to: '/automation',   keywords: 'automate routine' },
    { id: 'notes',    label: 'Notebook',      icon: FileText,         to: '/notebook',     keywords: 'notes scratch' },
    { id: 'dash',     label: 'Dashboard',     icon: LayoutDashboard,  to: '/dashboard',    keywords: 'overview home' },
    { id: 'settings', label: 'Settings',      icon: SettingsIcon,     to: '/settings',     keywords: 'preferences config speed mode' },
];

function matches(item: PaletteItem, query: string): boolean {
    if (!query) return true;
    const haystack = `${item.label} ${item.keywords ?? ''} ${item.to}`.toLowerCase();
    return query.toLowerCase().split(/\s+/).filter(Boolean).every((token) => haystack.includes(token));
}

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [activeIdx, setActiveIdx] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);

    const filtered = useMemo(() => ITEMS.filter((it) => matches(it, query)), [query]);

    useEffect(() => {
        if (!open) return;
        setQuery('');
        setActiveIdx(0);
        const t = setTimeout(() => inputRef.current?.focus(), 0);
        return () => clearTimeout(t);
    }, [open]);

    useEffect(() => {
        setActiveIdx(0);
    }, [query]);

    if (!open) return null;

    const choose = (item: PaletteItem | undefined) => {
        if (!item) return;
        onClose();
        navigate(item.to);
    };

    const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            onClose();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveIdx((i) => Math.max(0, i - 1));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            choose(filtered[activeIdx]);
        }
    };

    return (
        <div
            className="fixed inset-0 z-[100] flex items-start justify-center bg-black/40 backdrop-blur-sm pt-[15vh] px-4 animate-fade-in"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
        >
            <div
                className="w-full max-w-md rounded-card border border-surface-4 bg-surface-1 shadow-2xl overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center gap-2 border-b border-surface-4 px-3 py-2.5">
                    <Search size={14} className="text-text-muted shrink-0" />
                    <input
                        ref={inputRef}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={onKeyDown}
                        placeholder="Jump to a page or action…"
                        className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted focus:outline-none"
                        spellCheck={false}
                        autoComplete="off"
                    />
                    <kbd className="hidden sm:inline rounded-badge border border-surface-4 bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
                        Esc
                    </kbd>
                </div>
                <ul className="max-h-80 overflow-y-auto py-1">
                    {filtered.length === 0 && (
                        <li className="px-3 py-6 text-center text-xs text-text-muted">No matches.</li>
                    )}
                    {filtered.map((item, idx) => {
                        const Icon = item.icon;
                        const active = idx === activeIdx;
                        return (
                            <li key={item.id}>
                                <button
                                    type="button"
                                    onMouseEnter={() => setActiveIdx(idx)}
                                    onClick={() => choose(item)}
                                    className={cn(
                                        'w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors',
                                        active
                                            ? 'bg-accent/10 text-text-primary'
                                            : 'text-text-secondary hover:bg-surface-2',
                                    )}
                                >
                                    <Icon size={14} className={active ? 'text-accent' : 'text-text-muted'} />
                                    <span className="flex-1 truncate">{item.label}</span>
                                    <span className="font-mono text-[10px] text-text-muted">{item.to}</span>
                                </button>
                            </li>
                        );
                    })}
                </ul>
                <div className="flex items-center justify-between border-t border-surface-4 bg-surface-0 px-3 py-1.5 text-[10px] text-text-muted">
                    <span>↑↓ navigate · Enter open</span>
                    <span className="font-mono">⌘/Ctrl + K</span>
                </div>
            </div>
        </div>
    );
}
