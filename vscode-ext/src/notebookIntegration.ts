import * as vscode from 'vscode';

export function setupNotebookIntegration(context: vscode.ExtensionContext) {
    // CodeLens provider for Jupyter notebook cells
    const codeLensProvider = new NotebookCodeLensProvider();
    context.subscriptions.push(
        vscode.languages.registerCodeLensProvider(
            { language: 'python', scheme: 'vscode-notebook-cell' },
            codeLensProvider,
        ),
    );
}

class NotebookCodeLensProvider implements vscode.CodeLensProvider {
    provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
        const range = new vscode.Range(0, 0, 0, 0);
        return [
            new vscode.CodeLens(range, {
                title: 'Ask AI',
                command: 'private-ai.openChat',
            }),
            new vscode.CodeLens(range, {
                title: 'Fix',
                command: 'private-ai.fixBug',
            }),
        ];
    }
}
