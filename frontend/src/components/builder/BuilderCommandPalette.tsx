import { useEffect, useMemo, useState } from 'react';

export type BuilderPaletteAction = {
    id: string;
    label: string;
    hint?: string;
    run: () => void;
};

export function BuilderCommandPalette({
    open,
    onClose,
    actions,
}: {
    open: boolean;
    onClose: () => void;
    actions: BuilderPaletteAction[];
}) {
    const [q, setQ] = useState('');

    useEffect(() => {
        if (!open) setQ('');
    }, [open]);

    const filtered = useMemo(() => {
        const needle = q.trim().toLowerCase();
        if (!needle) return actions;
        return actions.filter(
            (a) =>
                a.label.toLowerCase().includes(needle) ||
                (a.hint && a.hint.toLowerCase().includes(needle)) ||
                a.id.includes(needle),
        );
    }, [actions, q]);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                onClose();
            }
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [open, onClose]);

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-[100] flex items-start justify-center bg-black/50 pt-[12vh] px-4"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div className="w-full max-w-2xl overflow-hidden border border-surface-4 bg-surface-1 shadow-none" onMouseDown={(e) => e.stopPropagation()}>
                <div className="border-b border-surface-4 px-3 py-2">
                    <input
                        autoFocus
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        placeholder="Type a command… (Esc to close)"
                        className="w-full border border-surface-4 bg-surface-0 px-2 py-1.5 text-sm text-text-primary outline-none focus:border-accent"
                    />
                    <p className="mt-1 text-[10px] text-text-muted">
                        Builder shortcuts are suppressed while focus is in inputs or the editor, except this palette (Ctrl+Shift+P).
                    </p>
                </div>
                <ul className="max-h-72 overflow-auto py-1">
                    {filtered.length === 0 && <li className="px-3 py-2 text-xs text-text-muted">No matches.</li>}
                    {filtered.map((a) => (
                        <li key={a.id}>
                            <button
                                type="button"
                                className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-xs hover:bg-surface-2"
                                onClick={() => {
                                    a.run();
                                    onClose();
                                }}
                            >
                                <span className="text-text-primary">{a.label}</span>
                                {a.hint && <span className="text-[10px] text-text-muted">{a.hint}</span>}
                            </button>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}
