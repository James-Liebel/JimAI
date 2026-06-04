/**
 * Presentational chrome for the Builder page: the top title/status bar and the
 * left activity bar. Extracted from `pages/Builder.tsx` to keep the page focused
 * on state and the editor/panel layout. Pure components — all behaviour comes in
 * through callbacks.
 */
import { Bot, Files, GitBranch, Keyboard, Maximize2, Search, Terminal } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '../../lib/utils';

type SidebarTab = 'explorer' | 'search' | 'source-control';

type BuilderTopBarProps = {
    minimalChrome: boolean;
    teamLabel: string;
    activeRunId: string;
    runStatusLabel: string;
    builderFullLayout: boolean;
    onGit: () => void;
    onOpenShortcuts: () => void;
};

export function BuilderTopBar({
    minimalChrome,
    teamLabel,
    activeRunId,
    runStatusLabel,
    builderFullLayout,
    onGit,
    onOpenShortcuts,
}: BuilderTopBarProps) {
    if (minimalChrome) return null;
    return (
        <div className="flex h-8 shrink-0 items-center gap-2 border-b border-[#2A2A30] bg-[#1A1A1E] px-2.5 text-[11px] text-text-secondary">
            <span className="shrink-0 text-sm font-medium text-text-primary">Builder</span>
            <span className="hidden min-w-0 flex-1 items-center gap-2 truncate sm:flex">
                <span className="text-text-muted">·</span>
                <span className="truncate text-[11px] text-text-muted">{teamLabel}</span>
                {activeRunId && (
                    <>
                        <span className="text-text-muted">·</span>
                        <span className="shrink-0 text-[11px] text-text-muted">
                            {runStatusLabel} · {activeRunId.slice(0, 8)}
                        </span>
                    </>
                )}
            </span>
            <div className="ml-auto flex shrink-0 items-center gap-1">
                <button
                    type="button"
                    onClick={onGit}
                    className="px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
                    title="Open source control in sidebar (Ctrl+Shift+G). Use Expand there for a larger panel."
                >
                    Git
                </button>
                <button
                    type="button"
                    onClick={onOpenShortcuts}
                    className="flex h-7 w-7 items-center justify-center text-text-muted hover:bg-white/[0.06] hover:text-text-primary"
                    title="Keyboard shortcuts"
                    aria-label="Keyboard shortcuts"
                >
                    <Keyboard size={15} strokeWidth={1.5} aria-hidden />
                </button>
                {builderFullLayout ? (
                    <Link
                        to="/builder"
                        className="px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
                        title="Show app navigation bar"
                    >
                        Exit full
                    </Link>
                ) : (
                    <Link
                        to="/builder?full=1"
                        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
                        title="Hide app nav"
                    >
                        <Maximize2 size={12} aria-hidden />
                        <span className="hidden sm:inline">Full</span>
                    </Link>
                )}
            </div>
        </div>
    );
}

const activityBtnClass = (active: boolean) =>
    cn(
        'flex h-11 w-11 shrink-0 items-center justify-center transition-colors duration-150',
        active ? 'border-l-2 border-l-[#3B82F6] bg-[#3B82F6]/8 text-text-primary' : 'text-text-muted hover:bg-[#222228] hover:text-text-secondary',
    );

type BuilderActivityBarProps = {
    showSidePanels: boolean;
    sidebarOpen: boolean;
    sidebarTab: SidebarTab;
    bottomPanelOpen: boolean;
    rightPanelOpen: boolean;
    onSelectSidebarTab: (tab: SidebarTab) => void;
    onToggleBottom: () => void;
    onToggleRight: () => void;
};

export function BuilderActivityBar({
    showSidePanels,
    sidebarOpen,
    sidebarTab,
    bottomPanelOpen,
    rightPanelOpen,
    onSelectSidebarTab,
    onToggleBottom,
    onToggleRight,
}: BuilderActivityBarProps) {
    return (
        <nav
            className="flex w-12 shrink-0 flex-col items-center gap-0.5 border-r border-[#2A2A30] bg-[#1A1A1E] py-1"
            aria-label="Activity bar"
        >
            {showSidePanels && (
                <>
                    <button
                        type="button"
                        className={activityBtnClass(sidebarOpen && sidebarTab === 'explorer')}
                        title="Explorer (Ctrl+Shift+E)"
                        onClick={() => onSelectSidebarTab('explorer')}
                    >
                        <Files size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                        type="button"
                        className={activityBtnClass(sidebarOpen && sidebarTab === 'search')}
                        title="Search — Find files & text (Ctrl+Shift+F)"
                        onClick={() => onSelectSidebarTab('search')}
                    >
                        <Search size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                    <button
                        type="button"
                        className={activityBtnClass(sidebarOpen && sidebarTab === 'source-control')}
                        title="Source Control (Ctrl+Shift+G)"
                        onClick={() => onSelectSidebarTab('source-control')}
                    >
                        <GitBranch size={20} strokeWidth={1.5} aria-hidden />
                    </button>
                </>
            )}
            <div className="min-h-2 flex-1" />
            <button
                type="button"
                className={activityBtnClass(bottomPanelOpen)}
                title="Toggle panel — Terminal (Ctrl+` or Ctrl+J)"
                onClick={onToggleBottom}
            >
                <Terminal size={20} strokeWidth={1.5} aria-hidden />
            </button>
            {showSidePanels && (
                <button
                    type="button"
                    className={activityBtnClass(rightPanelOpen)}
                    title="Toggle AI sidebar (Ctrl+L)"
                    onClick={onToggleRight}
                >
                    <Bot size={20} strokeWidth={1.5} aria-hidden />
                </button>
            )}
        </nav>
    );
}
