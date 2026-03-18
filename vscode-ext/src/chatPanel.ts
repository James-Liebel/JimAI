import * as vscode from 'vscode';

export class ChatPanel {
    public static currentPanel: ChatPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private readonly backendUrl: string;
    private disposables: vscode.Disposable[] = [];

    static createOrShow(extensionUri: vscode.Uri, backendUrl: string): ChatPanel {
        if (ChatPanel.currentPanel) {
            ChatPanel.currentPanel.panel.reveal(vscode.ViewColumn.Beside);
            return ChatPanel.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            'privateAiChat',
            'Private AI Chat',
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            },
        );

        ChatPanel.currentPanel = new ChatPanel(panel, backendUrl);
        return ChatPanel.currentPanel;
    }

    private constructor(panel: vscode.WebviewPanel, backendUrl: string) {
        this.panel = panel;
        this.backendUrl = backendUrl;

        this.panel.webview.html = this.getHtml();

        // Handle messages from webview
        this.panel.webview.onDidReceiveMessage(
            async (message) => {
                if (message.type === 'CHAT') {
                    await this.handleChat(message.content, message.mode);
                }
            },
            null,
            this.disposables,
        );

        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    }

    private async handleChat(content: string, mode: string): Promise<void> {
        try {
            const resp = await fetch(`${this.backendUrl}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: content,
                    mode,
                    session_id: 'vscode',
                    history: [],
                }),
            });

            if (!resp.body) return;
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value, { stream: true });
                const lines = text.split('\n');

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.text) {
                            this.panel.webview.postMessage({
                                type: 'CHUNK',
                                text: data.text,
                            });
                        }
                        if (data.done) {
                            this.panel.webview.postMessage({ type: 'DONE' });
                        }
                    } catch { }
                }
            }
        } catch (err) {
            this.panel.webview.postMessage({
                type: 'ERROR',
                text: `Error: ${err}`,
            });
        }
    }

    private getHtml(): string {
        return `<!DOCTYPE html>
<html>
<head>
  <style>
    body { font-family: var(--vscode-font-family); background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); padding: 12px; margin: 0; }
    #messages { overflow-y: auto; max-height: calc(100vh - 120px); }
    .msg { margin: 8px 0; padding: 8px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
    .user { background: var(--vscode-button-background); color: var(--vscode-button-foreground); margin-left: 20%; }
    .assistant { background: var(--vscode-editorWidget-background); margin-right: 20%; }
    #input-area { position: fixed; bottom: 0; left: 0; right: 0; padding: 8px 12px; background: var(--vscode-editor-background); border-top: 1px solid var(--vscode-panel-border); display: flex; gap: 8px; }
    #input { flex: 1; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); padding: 6px 10px; border-radius: 6px; font-size: 13px; }
    #send { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; }
    select { background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground); border: 1px solid var(--vscode-dropdown-border); padding: 4px; border-radius: 4px; font-size: 11px; }
  </style>
</head>
<body>
  <div id="messages"></div>
  <div id="input-area">
    <select id="mode">
      <option value="chat">Chat</option>
      <option value="code">Code</option>
      <option value="math">Math</option>
      <option value="writing">Writing</option>
    </select>
    <input id="input" placeholder="Ask Private AI..." />
    <button id="send">Send</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const messages = document.getElementById('messages');
    const input = document.getElementById('input');
    const mode = document.getElementById('mode');
    let currentAssistant = null;

    function send() {
      const text = input.value.trim();
      if (!text) return;
      addMessage('user', text);
      currentAssistant = addMessage('assistant', '');
      vscode.postMessage({ type: 'CHAT', content: text, mode: mode.value });
      input.value = '';
    }

    function addMessage(role, text) {
      const div = document.createElement('div');
      div.className = 'msg ' + role;
      div.textContent = text;
      messages.appendChild(div);
      div.scrollIntoView({ behavior: 'smooth' });
      return div;
    }

    document.getElementById('send').onclick = send;
    input.onkeydown = (e) => { if (e.key === 'Enter') send(); };

    window.addEventListener('message', (e) => {
      const msg = e.data;
      if (msg.type === 'CHUNK' && currentAssistant) {
        currentAssistant.textContent += msg.text;
        currentAssistant.scrollIntoView({ behavior: 'smooth' });
      }
      if (msg.type === 'DONE') {
        currentAssistant = null;
      }
      if (msg.type === 'ERROR') {
        addMessage('assistant', msg.text);
      }
    });
  </script>
</body>
</html>`;
    }

    dispose(): void {
        ChatPanel.currentPanel = undefined;
        this.panel.dispose();
        this.disposables.forEach((d) => d.dispose());
    }
}
