import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

interface IndexState {
    indexed_files: Record<string, number>;
    last_indexed: string;
}

export class RepoIndexer {
    private backendUrl: string;
    private indexPath: string;

    constructor(backendUrl: string) {
        this.backendUrl = backendUrl;
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
        this.indexPath = path.join(workspaceRoot, '.vscode', 'ai-index.json');
    }

    private loadState(): IndexState {
        try {
            if (fs.existsSync(this.indexPath)) {
                return JSON.parse(fs.readFileSync(this.indexPath, 'utf-8'));
            }
        } catch { }
        return { indexed_files: {}, last_indexed: '' };
    }

    private saveState(state: IndexState): void {
        const dir = path.dirname(this.indexPath);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(this.indexPath, JSON.stringify(state, null, 2));
    }

    async indexAll(): Promise<void> {
        const state = this.loadState();
        const pattern = '**/*.{py,ts,tsx,js,jsx,md,json}';
        const exclude = '**/node_modules/**';

        const files = await vscode.workspace.findFiles(pattern, exclude);

        await vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'Private AI: Indexing repository...',
                cancellable: false,
            },
            async (progress) => {
                let indexed = 0;
                for (const file of files) {
                    const relativePath = vscode.workspace.asRelativePath(file);
                    const stat = fs.statSync(file.fsPath);
                    const mtime = stat.mtimeMs;

                    // Skip if already indexed and not modified
                    if (state.indexed_files[relativePath] === mtime) continue;

                    try {
                        const content = fs.readFileSync(file.fsPath, 'utf-8');
                        const formData = new FormData();
                        const blob = new Blob([content], { type: 'text/plain' });
                        formData.append('file', blob, relativePath);
                        formData.append('session_id', 'vscode');

                        await fetch(`${this.backendUrl}/api/upload`, {
                            method: 'POST',
                            body: formData,
                        });

                        state.indexed_files[relativePath] = mtime;
                        indexed++;
                        progress.report({
                            message: `${indexed}/${files.length} files`,
                            increment: (1 / files.length) * 100,
                        });
                    } catch (err) {
                        console.warn(`Failed to index ${relativePath}:`, err);
                    }
                }

                state.last_indexed = new Date().toISOString();
                this.saveState(state);

                vscode.window.showInformationMessage(
                    `Private AI: Indexed ${indexed} file(s)`,
                );
            },
        );
    }

    async reindexFile(uri: vscode.Uri): Promise<void> {
        const relativePath = vscode.workspace.asRelativePath(uri);
        try {
            const content = fs.readFileSync(uri.fsPath, 'utf-8');
            const formData = new FormData();
            const blob = new Blob([content], { type: 'text/plain' });
            formData.append('file', blob, relativePath);
            formData.append('session_id', 'vscode');

            await fetch(`${this.backendUrl}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            const state = this.loadState();
            const stat = fs.statSync(uri.fsPath);
            state.indexed_files[relativePath] = stat.mtimeMs;
            this.saveState(state);
        } catch (err) {
            console.warn(`Failed to reindex ${relativePath}:`, err);
        }
    }
}
