import * as vscode from 'vscode';
import { RepoIndexer } from './repoIndexer';
import { ChatPanel } from './chatPanel';
import { PrivateAICompletionProvider } from './completionProvider';
import { DiagnosticsWatcher } from './diagnosticsWatcher';
import { AgentBuilderPanel } from './agentBuilder';
import * as commands from './commands';
import * as dataScience from './dataScience';

let repoIndexer: RepoIndexer;
let chatPanel: ChatPanel | undefined;

const MODE_CYCLE: Record<string, string> = {
    fast: 'balanced',
    balanced: 'deep',
    deep: 'fast',
};

const MODE_LABELS: Record<string, string> = {
    fast: '$(zap) Fast',
    balanced: '$(circle-filled) Balanced',
    deep: '$(beaker) Deep',
};

export function activate(context: vscode.ExtensionContext) {
    const backendUrl = vscode.workspace
        .getConfiguration('privateAI')
        .get<string>('backendUrl', 'http://localhost:8000');

    // Repo indexer
    repoIndexer = new RepoIndexer(backendUrl);
    repoIndexer.indexAll();

    // Status bar — main
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100,
    );
    statusBarItem.text = '$(robot) Private AI';
    statusBarItem.command = 'private-ai.openChat';
    statusBarItem.tooltip = 'Open Private AI Chat';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Status bar — speed mode
    const modeItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        99,
    );
    modeItem.command = 'private-ai.cycleSpeedMode';
    modeItem.tooltip = 'Click to cycle speed mode (Fast → Balanced → Deep)';
    modeItem.text = MODE_LABELS.balanced;
    modeItem.show();
    context.subscriptions.push(modeItem);

    async function fetchCurrentMode(): Promise<string> {
        try {
            const resp = await fetch(`${backendUrl}/api/settings/speed-mode`);
            const data = (await resp.json()) as { mode: string };
            return data.mode || 'balanced';
        } catch {
            return 'balanced';
        }
    }

    async function updateModeDisplay() {
        const mode = await fetchCurrentMode();
        modeItem.text = MODE_LABELS[mode] || MODE_LABELS.balanced;
    }

    updateModeDisplay();

    // Tab completion provider
    const completionProvider = new PrivateAICompletionProvider();
    context.subscriptions.push(
        vscode.languages.registerInlineCompletionItemProvider(
            [
                { language: 'python' },
                { language: 'typescript' },
                { language: 'javascript' },
                { language: 'typescriptreact' },
                { language: 'javascriptreact' },
                { language: 'r' },
                { language: 'sql' },
            ],
            completionProvider,
        ),
    );

    // Diagnostics watcher for lightbulb auto-fix
    const _diagWatcher = new DiagnosticsWatcher(backendUrl, context);

    // Register all commands
    context.subscriptions.push(
        vscode.commands.registerCommand('private-ai.openChat', () => {
            chatPanel = ChatPanel.createOrShow(context.extensionUri, backendUrl);
        }),
        vscode.commands.registerCommand('private-ai.explainFile', () =>
            commands.explainFile(backendUrl, context),
        ),
        vscode.commands.registerCommand('private-ai.fixBug', () =>
            commands.fixBug(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.writeTests', () =>
            commands.writeTests(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.refactorSelection', () =>
            commands.refactorSelection(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.indexRepo', () =>
            repoIndexer.indexAll(),
        ),
        vscode.commands.registerCommand('private-ai.commitWithMessage', () =>
            commands.commitWithMessage(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.openAgentBuilder', () => {
            AgentBuilderPanel.createOrShow(context.extensionUri, backendUrl);
        }),
        vscode.commands.registerCommand('private-ai.runCustomAgent', () =>
            commands.runCustomAgent(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.profileDataset', () =>
            dataScience.profileDataset(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.suggestMLModel', () =>
            dataScience.suggestMLModel(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.explainStatsOutput', () =>
            dataScience.explainStatsOutput(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.generateEDA', () =>
            dataScience.generateEDA(backendUrl),
        ),
        vscode.commands.registerCommand('private-ai.cycleSpeedMode', async () => {
            const current = await fetchCurrentMode();
            const next = MODE_CYCLE[current] || 'balanced';

            try {
                const resp = await fetch(`${backendUrl}/api/settings/speed-mode`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: next }),
                });
                const data = (await resp.json()) as { mode: string; warning?: string };
                modeItem.text = MODE_LABELS[data.mode] || MODE_LABELS.balanced;

                if (data.mode === 'deep') {
                    vscode.window.showWarningMessage(
                        'Deep mode: 32B model loaded. Slower responses, maximum capability.',
                    );
                }
            } catch (err) {
                vscode.window.showErrorMessage(`Failed to switch speed mode: ${err}`);
            }
        }),
    );

    // Re-index on file save
    vscode.workspace.onDidSaveTextDocument((doc) => {
        repoIndexer.reindexFile(doc.uri);
    });
}

export function deactivate() {
    chatPanel?.dispose();
}
