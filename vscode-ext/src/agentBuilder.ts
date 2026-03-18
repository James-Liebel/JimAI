import * as vscode from 'vscode';

export class AgentBuilderPanel {
    public static currentPanel: AgentBuilderPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private readonly backendUrl: string;
    private disposables: vscode.Disposable[] = [];

    static createOrShow(extensionUri: vscode.Uri, backendUrl: string) {
        if (AgentBuilderPanel.currentPanel) {
            AgentBuilderPanel.currentPanel.panel.reveal(vscode.ViewColumn.One);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'privateAIAgentBuilder',
            'Private AI Agent Builder',
            vscode.ViewColumn.One,
            { enableScripts: true, retainContextWhenHidden: true },
        );

        AgentBuilderPanel.currentPanel = new AgentBuilderPanel(panel, backendUrl);
    }

    private constructor(panel: vscode.WebviewPanel, backendUrl: string) {
        this.panel = panel;
        this.backendUrl = backendUrl;
        this.panel.webview.html = this.getHtml();

        this.panel.webview.onDidReceiveMessage(
            async (message) => {
                if (message.type === 'SAVE') {
                    await this.saveAgent(message.config);
                } else if (message.type === 'LOAD') {
                    await this.loadAgents();
                } else if (message.type === 'RUN') {
                    await this.runAgent(message.task);
                }
            },
            null,
            this.disposables,
        );

        this.panel.onDidDispose(() => {
            AgentBuilderPanel.currentPanel = undefined;
            this.disposables.forEach((d) => d.dispose());
        });

        this.loadAgents();
    }

    private async saveAgent(config: Record<string, unknown>) {
        try {
            await fetch(`${this.backendUrl}/api/agents/builder/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            vscode.window.showInformationMessage('Agent saved!');
        } catch (err) {
            vscode.window.showErrorMessage(`Failed to save agent: ${err}`);
        }
    }

    private async loadAgents() {
        try {
            const resp = await fetch(`${this.backendUrl}/api/agents/builder/list`);
            const data = await resp.json() as Record<string, unknown>;
            this.panel.webview.postMessage({ type: 'AGENTS', agents: data.agents });
        } catch {
            // ignore
        }
    }

    private async runAgent(task: string) {
        try {
            const resp = await fetch(`${this.backendUrl}/api/agents/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task, session_id: 'vscode-builder' }),
            });

            const reader = resp.body?.getReader();
            if (!reader) return;

            const decoder = new TextDecoder();
            let fullResult = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const text = decoder.decode(value, { stream: true });
                const lines = text.split('\n');
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.final_response) fullResult = data.final_response;
                        else if (data.step) {
                            this.panel.webview.postMessage({
                                type: 'STEP',
                                agent: data.agent,
                                step: data.step,
                                status: data.status,
                            });
                        }
                    } catch {
                        // skip
                    }
                }
            }

            this.panel.webview.postMessage({ type: 'RESULT', text: fullResult });
        } catch (err) {
            this.panel.webview.postMessage({ type: 'ERROR', text: String(err) });
        }
    }

    private getHtml(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: var(--vscode-font-family); background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); padding: 16px; }
        h1 { font-size: 18px; margin-bottom: 16px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
        label { font-size: 12px; display: block; margin-bottom: 4px; opacity: 0.7; }
        input, textarea, select { width: 100%; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 6px 8px; border-radius: 4px; font-size: 13px; }
        textarea { min-height: 60px; resize: vertical; }
        .btn { padding: 6px 14px; border-radius: 4px; border: none; cursor: pointer; font-size: 13px; margin-right: 8px; }
        .btn-primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
        .btn-secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
        .log { margin-top: 12px; padding: 8px; background: var(--vscode-terminal-background); border-radius: 4px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; }
        .log-entry { padding: 2px 0; }
        .status-running { color: #4f8ef7; }
        .status-done { color: #34d399; }
        .status-error { color: #f87171; }
    </style>
</head>
<body>
    <h1>⚡ Agent Builder</h1>
    <div class="grid">
        <div>
            <label>Agent Name</label>
            <input id="name" value="My Agent" />
        </div>
        <div>
            <label>Model</label>
            <select id="model">
                <option value="qwen3:8b">Chat (qwen3:8b)</option>
                <option value="qwen2.5-coder:7b">Code (qwen2.5-coder:7b)</option>
                <option value="qwen2-math:7b-instruct">Math (qwen2-math:7b-instruct)</option>
                <option value="qwen2.5vl:7b">Vision (qwen2.5vl:7b)</option>
            </select>
        </div>
    </div>
    <label>System Prompt</label>
    <textarea id="prompt" placeholder="Describe what this agent does..."></textarea>
    <br><br>
    <label>Test Task</label>
    <input id="task" placeholder="Enter a task to test..." />
    <br><br>
    <button class="btn btn-primary" id="save">Save Agent</button>
    <button class="btn btn-secondary" id="run">Test Agent</button>
    <div class="log" id="log"></div>
    <script>
        const vscode = acquireVsCodeApi();
        document.getElementById('save').onclick = () => {
            vscode.postMessage({
                type: 'SAVE',
                config: {
                    id: Date.now().toString(),
                    name: document.getElementById('name').value,
                    model: document.getElementById('model').value,
                    system_prompt: document.getElementById('prompt').value,
                    description: '', trigger: '', subagents: [], tools: [], max_iterations: 5
                }
            });
        };
        document.getElementById('run').onclick = () => {
            document.getElementById('log').innerHTML = '<div class="log-entry status-running">Running...</div>';
            vscode.postMessage({ type: 'RUN', task: document.getElementById('task').value });
        };
        window.addEventListener('message', (e) => {
            const msg = e.data;
            const log = document.getElementById('log');
            if (msg.type === 'STEP') {
                log.innerHTML += '<div class="log-entry status-' + msg.status + '">[' + msg.agent + '] ' + msg.step + '</div>';
                log.scrollTop = log.scrollHeight;
            }
            if (msg.type === 'RESULT') {
                log.innerHTML += '<div class="log-entry status-done">Result: ' + msg.text.substring(0, 500) + '</div>';
            }
            if (msg.type === 'ERROR') {
                log.innerHTML += '<div class="log-entry status-error">Error: ' + msg.text + '</div>';
            }
        });
    </script>
</body>
</html>`;
    }
}
