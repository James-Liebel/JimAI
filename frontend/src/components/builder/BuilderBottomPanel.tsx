/**
 * Bottom panel for the Builder page: the combined terminal + agent activity log
 * with a run-command input. Extracted from `pages/Builder.tsx`; renders nothing
 * when `open` is false.
 */
import { cn } from '../../lib/utils';
import { ResizeHandle } from './ResizeHandle';
import { formatTime, type ActivityRow } from './builderHelpers';

type BottomLogTab = 'all' | 'terminal' | 'agent';

type BuilderBottomPanelProps = {
    open: boolean;
    height: number;
    onResizeDelta: (dy: number) => void;
    onResizeCommit: () => void;
    logTab: BottomLogTab;
    onSelectLogTab: (tab: BottomLogTab) => void;
    terminalCwd: string;
    onTerminalCwdChange: (value: string) => void;
    terminalCommand: string;
    onTerminalCommandChange: (value: string) => void;
    onRunTerminal: () => void;
    runningTerminal: boolean;
    activityRows: ActivityRow[];
    filteredActivityRows: ActivityRow[];
};

export function BuilderBottomPanel({
    open,
    height,
    onResizeDelta,
    onResizeCommit,
    logTab,
    onSelectLogTab,
    terminalCwd,
    onTerminalCwdChange,
    terminalCommand,
    onTerminalCommandChange,
    onRunTerminal,
    runningTerminal,
    activityRows,
    filteredActivityRows,
}: BuilderBottomPanelProps) {
    if (!open) return null;
    return (
        <>
            <ResizeHandle axis="vertical" onDelta={onResizeDelta} onCommit={onResizeCommit} />
            <section className="shrink-0 border-t border-[#2A2A30] bg-[#111113]">
                <div className="flex flex-col gap-2 border-b border-[#2A2A30] px-2.5 py-1.5 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap items-center gap-0.5">
                        {(['all', 'terminal', 'agent'] as const).map((key) => (
                            <button
                                key={key}
                                type="button"
                                onClick={() => onSelectLogTab(key)}
                                className={cn(
                                    'rounded-badge px-2.5 py-1 text-[11px] font-medium transition-colors',
                                    logTab === key
                                        ? 'bg-[#1A1A1E] text-text-primary'
                                        : 'text-text-muted hover:text-text-secondary',
                                )}
                            >
                                {key === 'all' ? 'All' : key === 'terminal' ? 'Terminal' : 'Log'}
                            </button>
                        ))}
                    </div>
                    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 sm:justify-end">
                        <input
                            value={terminalCwd}
                            onChange={(e) => onTerminalCwdChange(e.target.value)}
                            className="w-28 rounded-btn border border-[#2A2A30] bg-[#0A0A0B] px-2 py-1 font-mono text-[11px] text-text-primary outline-none focus:border-[#3B82F6]"
                            placeholder="cwd"
                        />
                        <input
                            value={terminalCommand}
                            onChange={(e) => onTerminalCommandChange(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') onRunTerminal();
                            }}
                            className="min-w-[8rem] flex-1 rounded-btn border border-[#2A2A30] bg-[#0A0A0B] px-2 py-1 font-mono text-[11px] text-text-primary outline-none focus:border-[#3B82F6] sm:max-w-xs"
                            placeholder="Command…"
                        />
                        <button
                            type="button"
                            onClick={onRunTerminal}
                            disabled={runningTerminal}
                            className="shrink-0 rounded-btn border border-[#3B82F6]/35 px-2.5 py-1 text-[11px] font-medium text-[#3B82F6] transition-colors hover:bg-[#3B82F6]/10 disabled:opacity-50"
                        >
                            {runningTerminal ? 'Running…' : 'Run'}
                        </button>
                    </div>
                </div>
                <div
                    style={{ height }}
                    className="overflow-auto px-3 py-2 font-mono text-[11px] leading-5 text-text-secondary"
                >
                    {filteredActivityRows.length === 0 ? (
                        <p className="text-[11px] text-text-muted">
                            {activityRows.length === 0
                                ? 'No shell output or agent events yet.'
                                : 'Nothing in this filter.'}
                        </p>
                    ) : (
                        filteredActivityRows.map((row) => (
                            <div key={row.id} className="border-b border-[#2A2A30]/50 py-1.5 last:border-b-0">
                                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-text-muted">
                                    <span>{formatTime(row.timestamp)}</span>
                                    <span className="capitalize">{row.prefix}</span>
                                    <span className="text-text-secondary">{row.title}</span>
                                </div>
                                <pre className={cn('mt-0.5 whitespace-pre-wrap break-words', row.tone)}>
                                    {row.body || '(no output)'}
                                </pre>
                            </div>
                        ))
                    )}
                </div>
            </section>
        </>
    );
}
