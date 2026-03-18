import * as vscode from 'vscode';

export class PrivateAICompletionProvider implements vscode.InlineCompletionItemProvider {
    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        _context: vscode.InlineCompletionContext,
        _token: vscode.CancellationToken,
    ): Promise<vscode.InlineCompletionList> {
        const linePrefix = document.lineAt(position).text.substring(0, position.character);

        if (linePrefix.trim().length < 2) return { items: [] };
        if (linePrefix.trim().startsWith('#') || linePrefix.trim().startsWith('//')) return { items: [] };

        const startLine = Math.max(0, position.line - 10);
        const endLine = Math.min(document.lineCount - 1, position.line + 10);
        const contextText = document.getText(
            new vscode.Range(startLine, 0, endLine, 999),
        );

        try {
            const response = await fetch('http://localhost:8000/api/completion', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prefix: linePrefix,
                    context: contextText,
                    language: document.languageId,
                    cursor_position: linePrefix.length,
                }),
                signal: AbortSignal.timeout(500),
            });
            const data = (await response.json()) as { completions?: string[] };
            const completions: string[] = data.completions || [];
            return {
                items: completions.map((c) => ({
                    insertText: c,
                    range: new vscode.Range(position, position),
                })),
            };
        } catch {
            return { items: [] };
        }
    }
}
