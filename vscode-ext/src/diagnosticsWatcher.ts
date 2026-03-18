import * as vscode from 'vscode';

export class DiagnosticsWatcher implements vscode.CodeActionProvider {
    private backendUrl: string;

    constructor(backendUrl: string, context: vscode.ExtensionContext) {
        this.backendUrl = backendUrl;

        context.subscriptions.push(
            vscode.languages.registerCodeActionsProvider(
                [
                    { language: 'python' },
                    { language: 'typescript' },
                    { language: 'javascript' },
                    { language: 'typescriptreact' },
                    { language: 'javascriptreact' },
                ],
                this,
                { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] },
            ),
        );
    }

    provideCodeActions(
        document: vscode.TextDocument,
        range: vscode.Range,
    ): vscode.CodeAction[] {
        const diagnostics = vscode.languages.getDiagnostics(document.uri);
        const relevantDiags = diagnostics.filter(
            (d) =>
                d.severity === vscode.DiagnosticSeverity.Error &&
                d.range.intersection(range),
        );

        if (relevantDiags.length === 0) return [];

        const action = new vscode.CodeAction(
            'Fix with Private AI',
            vscode.CodeActionKind.QuickFix,
        );
        action.command = {
            command: 'private-ai.fixBug',
            title: 'Fix with Private AI',
        };
        action.diagnostics = relevantDiags;
        action.isPreferred = false;

        return [action];
    }
}
