/**
 * VS Code–style: chord shortcuts should not fire while typing in inputs or Monaco,
 * except for the command palette (Ctrl+Shift+P) which is handled separately.
 */
export function isShortcutFocusInEditorField(target: EventTarget | null): boolean {
    const el = target as HTMLElement | null;
    if (!el) return false;
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
    if (el.isContentEditable) return true;
    if (el.closest?.('.monaco-editor')) return true;
    return false;
}
