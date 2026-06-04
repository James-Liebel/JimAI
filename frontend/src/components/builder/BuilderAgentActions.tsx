import {
    Ban,
    Check,
    FileText,
    FolderUp,
    Globe,
    Loader2,
    MessageSquare,
    Pencil,
    Search,
    Sparkles,
    Terminal,
    X,
    type LucideIcon,
} from 'lucide-react';
import { agentActionVerb, type AgentAction } from './builderHelpers';
import { cn } from '../../lib/utils';

interface Props {
    actions: AgentAction[];
    onOpenFile: (path: string) => void;
}

const ACTION_ICONS: Record<string, LucideIcon> = {
    read_file: FileText,
    write_file: Pencil,
    replace_in_file: Pencil,
    run_shell: Terminal,
    index_search: Search,
    web_search: Globe,
    web_fetch: Globe,
    self_improve: Sparkles,
    export: FolderUp,
    send_message: MessageSquare,
    read_messages: MessageSquare,
};

const FILE_ACTIONS = new Set(['read_file', 'write_file', 'replace_in_file', 'self_improve']);

function StatusIcon({ status }: { status: AgentAction['status'] }) {
    if (status === 'running') return <Loader2 className="h-3 w-3 shrink-0 animate-spin text-accent" aria-hidden />;
    if (status === 'failed') return <X className="h-3 w-3 shrink-0 text-accent-red" aria-hidden />;
    if (status === 'denied') return <Ban className="h-3 w-3 shrink-0 text-accent-amber" aria-hidden />;
    return <Check className="h-3 w-3 shrink-0 text-accent-green" aria-hidden />;
}

/**
 * Cursor-style timeline of the agent's tool calls. Each `action.started`/
 * `.completed` pair from the run stream becomes a card: verb + target with a
 * live status. File targets are clickable and open in the editor.
 */
export function BuilderAgentActions({ actions, onOpenFile }: Props) {
    if (actions.length === 0) return null;

    return (
        <div className="space-y-1">
            <p className="px-0.5 text-[10px] font-medium uppercase tracking-[0.08em] text-text-muted">Actions</p>
            {actions.map((action) => {
                const Icon = ACTION_ICONS[action.type] || Terminal;
                const isFile = FILE_ACTIONS.has(action.type) && Boolean(action.target);
                const isShell = action.type === 'run_shell';
                const target = action.target.split('/').pop() || action.target;

                return (
                    <div
                        key={action.id}
                        className={cn(
                            'rounded-md border px-2 py-1.5 text-[11px] transition-colors',
                            action.status === 'failed'
                                ? 'border-accent-red/30 bg-accent-red/[0.06]'
                                : action.status === 'denied'
                                  ? 'border-accent-amber/30 bg-accent-amber/[0.06]'
                                  : action.status === 'running'
                                    ? 'border-accent/30 bg-accent/[0.06]'
                                    : 'border-[#2A2A30] bg-[#1A1A1E]',
                        )}
                    >
                        <div className="flex items-center gap-1.5">
                            <StatusIcon status={action.status} />
                            <Icon className="h-3 w-3 shrink-0 text-text-muted" aria-hidden />
                            <span className="shrink-0 font-medium text-text-secondary">{agentActionVerb(action.type)}</span>
                            {action.target && (
                                isFile ? (
                                    <button
                                        type="button"
                                        onClick={() => onOpenFile(action.target)}
                                        title={action.target}
                                        className="min-w-0 truncate font-mono text-[10px] text-accent hover:underline"
                                    >
                                        {target}
                                    </button>
                                ) : (
                                    <span
                                        title={action.target}
                                        className={cn(
                                            'min-w-0 truncate font-mono text-[10px] text-text-primary',
                                            isShell && 'rounded bg-black/30 px-1 py-0.5',
                                        )}
                                    >
                                        {action.target}
                                    </span>
                                )
                            )}
                        </div>
                        {action.detail && (
                            <p
                                className={cn(
                                    'mt-1 truncate pl-[18px] font-mono text-[10px]',
                                    action.status === 'failed' || action.status === 'denied' ? 'text-accent-red/80' : 'text-text-muted',
                                )}
                                title={action.detail}
                            >
                                {action.detail}
                            </p>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
