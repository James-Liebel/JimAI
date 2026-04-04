import { PanelTop } from 'lucide-react';
import { cn } from '../../lib/utils';

export function BuilderStatusBar({
    fileLabel,
    lineCol,
    language,
    branch,
    notice,
    minimalChrome = false,
    onRestoreTopBar,
}: {
    fileLabel: string;
    lineCol: string;
    language: string;
    branch: string;
    notice: { type: 'ok' | 'error'; text: string } | null;
    minimalChrome?: boolean;
    onRestoreTopBar?: () => void;
}) {
    return (
        <div className="flex h-7 shrink-0 items-center gap-2 border-t border-white/[0.08] bg-[#1e1e1e] px-2 text-[11px] text-text-secondary">
            {minimalChrome && onRestoreTopBar && (
                <div className="flex shrink-0 items-center border-r border-white/10 pr-2">
                    <button
                        type="button"
                        onClick={onRestoreTopBar}
                        className="flex h-6 w-6 items-center justify-center text-text-muted hover:bg-white/[0.06] hover:text-text-primary"
                        title="Show top bar"
                        aria-label="Show top bar"
                    >
                        <PanelTop size={14} strokeWidth={1.5} aria-hidden />
                    </button>
                </div>
            )}
            <span className="min-w-0 flex-1 truncate font-mono text-text-primary" title={fileLabel}>
                {fileLabel}
            </span>
            {notice && (
                <span
                    className={cn(
                        'max-w-[40%] truncate',
                        notice.type === 'error' ? 'text-accent-red' : 'text-accent-green',
                    )}
                    title={notice.text}
                >
                    {notice.text}
                </span>
            )}
            <span className="hidden shrink-0 sm:inline">{lineCol}</span>
            <span className="shrink-0 capitalize">{language}</span>
            <span className="shrink-0 text-text-muted">{branch || '—'}</span>
        </div>
    );
}
