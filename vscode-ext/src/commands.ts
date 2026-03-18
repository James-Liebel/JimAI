import * as vscode from 'vscode';
import { ChatPanel } from './chatPanel';

/**
 * Explain the currently active file.
 */
export async function explainFile(
    backendUrl: string,
    context: vscode.ExtensionContext,
): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('No active file to explain');
        return;
    }

    const content = editor.document.getText();
    const filename = editor.document.fileName;

    const panel = ChatPanel.createOrShow(context.extensionUri, backendUrl);

    try {
        const resp = await fetch(`${backendUrl}/api/agents/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task: `Explain this file: ${filename}\n\n${content.slice(0, 8000)}`,
                session_id: 'vscode',
            }),
        });

        if (!resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            // Parse SSE and forward to chat panel
        }
    } catch (err) {
        vscode.window.showErrorMessage(`Private AI: ${err}`);
    }
}

/**
 * Fix bugs in the active file using diagnostics.
 */
export async function fixBug(backendUrl: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('No active file');
        return;
    }

    const content = editor.document.getText();
    const diagnostics = vscode.languages.getDiagnostics(editor.document.uri);
    const errors = diagnostics
        .filter((d) => d.severity === vscode.DiagnosticSeverity.Error)
        .map((d) => `Line ${d.range.start.line + 1}: ${d.message}`)
        .join('\n');

    if (!errors) {
        vscode.window.showInformationMessage('No errors found in this file');
        return;
    }

    try {
        const resp = await fetch(`${backendUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: `Fix these errors in the code:\n\nErrors:\n${errors}\n\nCode:\n${content.slice(0, 8000)}`,
                mode: 'code',
                session_id: 'vscode',
                history: [],
            }),
        });

        if (!resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) fullResponse += data.text;
                } catch { }
            }
        }

        // Show result in output channel
        const channel = vscode.window.createOutputChannel('Private AI');
        channel.appendLine(fullResponse);
        channel.show();
    } catch (err) {
        vscode.window.showErrorMessage(`Private AI: ${err}`);
    }
}

/**
 * Write tests for selected code.
 */
export async function writeTests(backendUrl: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const selection = editor.document.getText(editor.selection);
    if (!selection) {
        vscode.window.showWarningMessage('Select the code you want to write tests for');
        return;
    }

    try {
        const resp = await fetch(`${backendUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: `Write comprehensive tests for this function:\n\n${selection}`,
                mode: 'code',
                session_id: 'vscode',
                history: [],
            }),
        });

        if (!resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) fullResponse += data.text;
                } catch { }
            }
        }

        const channel = vscode.window.createOutputChannel('Private AI');
        channel.appendLine(fullResponse);
        channel.show();
    } catch (err) {
        vscode.window.showErrorMessage(`Private AI: ${err}`);
    }
}

/**
 * Refactor selected code with user instruction.
 */
export async function refactorSelection(backendUrl: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const selection = editor.document.getText(editor.selection);
    if (!selection) {
        vscode.window.showWarningMessage('Select the code you want to refactor');
        return;
    }

    const instruction = await vscode.window.showInputBox({
        prompt: 'How should this be refactored?',
        placeHolder: 'e.g., Make this more efficient, Add error handling',
    });

    if (!instruction) return;

    try {
        const resp = await fetch(`${backendUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: `Refactor this code: ${instruction}\n\n${selection}`,
                mode: 'code',
                session_id: 'vscode',
                history: [],
            }),
        });

        if (!resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) fullResponse += data.text;
                } catch { }
            }
        }

        // Extract code blocks from response and replace selection
        const codeMatch = fullResponse.match(/```[\w]*\n([\s\S]*?)```/);
        if (codeMatch) {
            await editor.edit((editBuilder) => {
                editBuilder.replace(editor.selection, codeMatch[1].trim());
            });
        } else {
            const channel = vscode.window.createOutputChannel('Private AI');
            channel.appendLine(fullResponse);
            channel.show();
        }
    } catch (err) {
        vscode.window.showErrorMessage(`Private AI: ${err}`);
    }
}

/**
 * Generate a commit message from the current git diff.
 */
export async function commitWithMessage(backendUrl: string): Promise<void> {
    const { exec } = require('child_process');
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

    if (!workspaceRoot) {
        vscode.window.showWarningMessage('No workspace folder open');
        return;
    }

    // Get git diff
    const getDiff = (): Promise<string> =>
        new Promise((resolve) => {
            exec(
                'git diff --staged',
                { cwd: workspaceRoot },
                (_err: Error | null, stdout: string) => resolve(stdout || ''),
            );
        });

    const diff = await getDiff();
    if (!diff) {
        vscode.window.showWarningMessage(
            'No staged changes. Stage files first with git add.',
        );
        return;
    }

    try {
        const resp = await fetch(`${backendUrl}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: `Write a conventional commit message for this diff. Return ONLY the commit message, nothing else:\n\n${diff.slice(0, 5000)}`,
                mode: 'code',
                session_id: 'vscode',
                history: [],
            }),
        });

        if (!resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let commitMsg = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) commitMsg += data.text;
                } catch { }
            }
        }

        // Set the commit message in the SCM input
        const gitExtension = vscode.extensions.getExtension('vscode.git');
        if (gitExtension) {
            const git = gitExtension.exports.getAPI(1);
            const repo = git.repositories[0];
            if (repo) {
                repo.inputBox.value = commitMsg.trim();
                vscode.window.showInformationMessage(
                    'Private AI: Commit message generated! Review and commit.',
                );
            }
        }
    } catch (err) {
        vscode.window.showErrorMessage(`Private AI: ${err}`);
    }
}

/**
 * Pick a saved agent and run it on the current repo.
 */
export async function runCustomAgent(backendUrl: string): Promise<void> {
    try {
        const resp = await fetch(`${backendUrl}/api/agents/builder/list`);
        const data = await resp.json() as { agents: Array<{ id: string; name: string }> };

        if (!data.agents || data.agents.length === 0) {
            vscode.window.showInformationMessage('No saved agents. Create one in Agent Builder first.');
            return;
        }

        const picked = await vscode.window.showQuickPick(
            data.agents.map((a) => ({ label: a.name, id: a.id })),
            { placeHolder: 'Select an agent to run' },
        );
        if (!picked) return;

        const task = await vscode.window.showInputBox({
            prompt: `Task for ${picked.label}`,
            placeHolder: 'Describe the task...',
        });
        if (!task) return;

        const channel = vscode.window.createOutputChannel('Private AI - Agent');
        channel.show();
        channel.appendLine(`Running agent: ${picked.label}`);
        channel.appendLine(`Task: ${task}\n`);

        const runResp = await fetch(`${backendUrl}/api/agents/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task, session_id: 'vscode-agent' }),
        });

        if (!runResp.body) return;
        const reader = runResp.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            for (const line of text.split('\n')) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const stepData = JSON.parse(line.slice(6));
                    channel.appendLine(`[${stepData.agent}] ${stepData.step} (${stepData.status})`);
                    if (stepData.final_response) {
                        channel.appendLine(`\nResult:\n${stepData.final_response}`);
                    }
                } catch { /* skip */ }
            }
        }
    } catch (err) {
        vscode.window.showErrorMessage(`Private AI: ${err}`);
    }
}
