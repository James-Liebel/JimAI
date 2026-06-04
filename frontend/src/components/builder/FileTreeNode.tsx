/**
 * Recursive workspace file-tree row for the Builder explorer / search panels.
 * Extracted verbatim from `pages/Builder.tsx`.
 */
import { ChevronRight } from 'lucide-react';
import * as agentApi from '../../lib/agentSpaceApi';
import { cn } from '../../lib/utils';
import type { PendingCreate } from './builderHelpers';

type FileTreeNodeProps = {
    node: agentApi.RepoTreeNode;
    depth: number;
    selectedDirectory: string;
    selectedFilePath: string;
    pendingCreate: PendingCreate | null;
    onOpenFile: (path: string) => void;
    onSelectDirectory: (path: string) => void;
    onRequestCreate: (parentPath: string, kind: 'file' | 'folder') => void;
    onChangePendingValue: (value: string) => void;
    onCreate: () => void | Promise<void>;
    onCancelCreate: () => void;
    creatingNode: boolean;
    writeMode: 'direct' | 'review';
    expandedDirs?: Set<string>;
    onToggleDir?: (path: string) => void;
    showCreateActions?: boolean;
};

export function FileTreeNode({
    node,
    depth,
    selectedDirectory,
    selectedFilePath,
    pendingCreate,
    onOpenFile,
    onSelectDirectory,
    onRequestCreate,
    onChangePendingValue,
    onCreate,
    onCancelCreate,
    creatingNode,
    writeMode,
    expandedDirs,
    onToggleDir,
    showCreateActions = true,
}: FileTreeNodeProps) {
    if (node.type === 'file') {
        return (
            <button
                type="button"
                onClick={() => onOpenFile(node.path)}
                className={cn('flex w-full items-center rounded-none px-2 py-1 text-left text-xs', selectedFilePath === node.path ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:bg-surface-2')}
                style={{ paddingLeft: `${depth * 14 + 10}px` }}
            >
                <span className="truncate">{node.name}</span>
            </button>
        );
    }
    const children = Array.isArray(node.children) ? node.children : [];
    const isSelected = selectedDirectory === node.path;
    const showInlineCreate = pendingCreate?.parentPath === node.path;
    const controlled = expandedDirs != null && onToggleDir != null;
    const isOpen = controlled
        ? expandedDirs.has(node.path)
        : depth < 1 || selectedDirectory.startsWith(node.path === '.' ? '' : `${node.path}/`) || isSelected;

    const rowPad = `${depth * 14 + 8}px`;
    const createRow = showInlineCreate && (
        <div className="px-2 py-1" style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}>
            <div className="rounded-none border border-surface-4 bg-surface-0 p-2">
                <p className="text-[10px] text-text-secondary">
                    New {pendingCreate!.kind} in {pendingCreate!.parentPath} · {writeMode === 'review' && pendingCreate!.kind === 'file' ? 'submit to review' : 'write directly'}
                </p>
                <input
                    value={pendingCreate!.value}
                    onChange={(e) => onChangePendingValue(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') onCreate();
                        if (e.key === 'Escape') onCancelCreate();
                    }}
                    className="mt-2 w-full rounded-none border border-surface-4 bg-surface-0 px-2 py-1 text-[11px] text-text-primary outline-none"
                    placeholder={`Enter ${pendingCreate!.kind} name`}
                />
                <div className="mt-2 flex gap-2">
                    <button type="button" onClick={() => onCreate()} disabled={creatingNode} className="rounded-none border border-accent/40 px-2 py-1 text-[10px] text-accent disabled:opacity-50">
                        {creatingNode ? (writeMode === 'review' && pendingCreate!.kind === 'file' ? 'Submitting…' : 'Creating…') : writeMode === 'review' && pendingCreate!.kind === 'file' ? 'Submit Review' : 'Create'}
                    </button>
                    <button type="button" onClick={onCancelCreate} className="rounded-none border border-surface-4 px-2 py-1 text-[10px] text-text-secondary hover:bg-surface-2">
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );

    if (controlled) {
        return (
            <div className="mb-0.5">
                <div className={cn('flex items-center gap-0.5 rounded-none py-1 text-xs', isSelected ? 'bg-surface-2 text-text-primary' : 'text-text-primary')} style={{ paddingLeft: rowPad }}>
                    <button
                        type="button"
                        className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-text-muted hover:bg-surface-3 hover:text-text-primary"
                        aria-expanded={isOpen}
                        onClick={(e) => {
                            e.stopPropagation();
                            onToggleDir(node.path);
                        }}
                    >
                        <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', isOpen && 'rotate-90')} aria-hidden />
                    </button>
                    <button type="button" onClick={() => onSelectDirectory(node.path)} className="min-w-0 flex-1 truncate rounded px-1 py-0.5 text-left hover:bg-surface-2/80">
                        {node.name}
                    </button>
                    {showCreateActions && (
                        <span className="flex shrink-0 items-center gap-0.5 pr-1">
                            <button
                                type="button"
                                onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    onSelectDirectory(node.path);
                                    onRequestCreate(node.path, 'file');
                                }}
                                className="px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary"
                                title="New file"
                            >
                                +F
                            </button>
                            <button
                                type="button"
                                onClick={(event) => {
                                    event.preventDefault();
                                    event.stopPropagation();
                                    onSelectDirectory(node.path);
                                    onRequestCreate(node.path, 'folder');
                                }}
                                className="px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary"
                                title="New folder"
                            >
                                +D
                            </button>
                        </span>
                    )}
                </div>
                {isOpen && (
                    <div className="mt-0.5">
                        {createRow}
                        {children.map((child) => (
                            <FileTreeNode
                                key={`${child.path}-${child.name}`}
                                node={child}
                                depth={depth + 1}
                                selectedDirectory={selectedDirectory}
                                selectedFilePath={selectedFilePath}
                                pendingCreate={pendingCreate}
                                onOpenFile={onOpenFile}
                                onSelectDirectory={onSelectDirectory}
                                onRequestCreate={onRequestCreate}
                                onChangePendingValue={onChangePendingValue}
                                onCreate={onCreate}
                                onCancelCreate={onCancelCreate}
                                creatingNode={creatingNode}
                                writeMode={writeMode}
                                expandedDirs={expandedDirs}
                                onToggleDir={onToggleDir}
                                showCreateActions={showCreateActions}
                            />
                        ))}
                    </div>
                )}
            </div>
        );
    }

    return (
        <details open={isOpen} className="mb-0.5">
            <summary
                className={cn('flex cursor-pointer list-none items-center justify-between gap-2 rounded-none px-2 py-1 text-xs', isSelected ? 'bg-surface-2 text-text-primary' : 'text-text-primary hover:bg-surface-2')}
                style={{ paddingLeft: rowPad }}
                onClick={() => onSelectDirectory(node.path)}
            >
                <span className="truncate">{node.name}</span>
                {showCreateActions && (
                    <span className="flex shrink-0 items-center gap-1">
                        <button
                            type="button"
                            onClick={(event) => {
                                event.preventDefault();
                                event.stopPropagation();
                                onSelectDirectory(node.path);
                                onRequestCreate(node.path, 'file');
                            }}
                            className="px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary"
                            title="New file"
                        >
                            +F
                        </button>
                        <button
                            type="button"
                            onClick={(event) => {
                                event.preventDefault();
                                event.stopPropagation();
                                onSelectDirectory(node.path);
                                onRequestCreate(node.path, 'folder');
                            }}
                            className="px-1 text-[10px] text-text-muted hover:bg-surface-3 hover:text-text-primary"
                            title="New folder"
                        >
                            +D
                        </button>
                    </span>
                )}
            </summary>
            <div className="mt-0.5">
                {createRow}
                {children.map((child) => (
                    <FileTreeNode
                        key={`${child.path}-${child.name}`}
                        node={child}
                        depth={depth + 1}
                        selectedDirectory={selectedDirectory}
                        selectedFilePath={selectedFilePath}
                        pendingCreate={pendingCreate}
                        onOpenFile={onOpenFile}
                        onSelectDirectory={onSelectDirectory}
                        onRequestCreate={onRequestCreate}
                        onChangePendingValue={onChangePendingValue}
                        onCreate={onCreate}
                        onCancelCreate={onCancelCreate}
                        creatingNode={creatingNode}
                        writeMode={writeMode}
                    />
                ))}
            </div>
        </details>
    );
}
