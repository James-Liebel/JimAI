/**
 * Keyboard-shortcuts reference dialog for the Builder page.
 * Extracted from `pages/Builder.tsx`; renders nothing when `open` is false.
 */
type BuilderShortcutsModalProps = {
    open: boolean;
    onClose: () => void;
    minimalChrome: boolean;
    onMinimalChromeChange: (value: boolean) => void;
};

export function BuilderShortcutsModal({ open, onClose, minimalChrome, onMinimalChromeChange }: BuilderShortcutsModalProps) {
    if (!open) return null;
    return (
        <div
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-4 pt-[10vh]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="builder-shortcuts-title"
        >
            <button
                type="button"
                className="absolute inset-0 cursor-default"
                aria-label="Close shortcuts"
                onClick={onClose}
            />
            <div className="relative z-10 w-full max-w-md border border-white/[0.1] bg-[#252526] p-4 shadow-none">
                <div className="flex items-start justify-between gap-2">
                    <h2 id="builder-shortcuts-title" className="text-sm font-medium text-text-primary">
                        Keyboard shortcuts
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        className="px-2 py-0.5 text-text-muted hover:bg-white/[0.06] hover:text-text-primary"
                    >
                        Esc
                    </button>
                </div>
                <ul className="mt-4 space-y-2.5 text-[12px] text-text-secondary">
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+P</kbd>{' '}
                        Command palette
                    </li>
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+B</kbd> Toggle sidebar
                    </li>
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+E</kbd> Explorer
                    </li>
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+F</kbd> Search
                    </li>
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+Shift+G</kbd> Source control
                    </li>
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+`</kbd> or{' '}
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+J</kbd> Bottom panel
                    </li>
                    <li>
                        <kbd className="border border-white/10 bg-[#1e1e1e] px-1.5 py-0.5 font-mono text-[11px]">Ctrl+L</kbd> AI sidebar
                    </li>
                </ul>
                <div className="mt-4 border-t border-white/[0.08] pt-4">
                    <label className="flex cursor-pointer items-center gap-2 text-[12px] text-text-secondary">
                        <input
                            type="checkbox"
                            className="h-3.5 w-3.5 border border-white/20 bg-[#1e1e1e]"
                            checked={minimalChrome}
                            onChange={(e) => onMinimalChromeChange(e.target.checked)}
                        />
                        Minimal chrome (hide top bar)
                    </label>
                </div>
            </div>
        </div>
    );
}
