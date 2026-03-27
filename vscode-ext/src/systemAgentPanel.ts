import * as vscode from 'vscode';

export class SystemAgentPanel {
    public static currentPanel: SystemAgentPanel | undefined;
    private readonly panel: vscode.WebviewPanel;
    private readonly disposables: vscode.Disposable[] = [];

    static createOrShow(): SystemAgentPanel {
        if (SystemAgentPanel.currentPanel) {
            SystemAgentPanel.currentPanel.panel.reveal(vscode.ViewColumn.Two);
            return SystemAgentPanel.currentPanel;
        }

        const panel = vscode.window.createWebviewPanel(
            'privateAiSystemAgent',
            'Private AI - System Agent',
            vscode.ViewColumn.Two,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            },
        );

        SystemAgentPanel.currentPanel = new SystemAgentPanel(panel);
        return SystemAgentPanel.currentPanel;
    }

    private constructor(panel: vscode.WebviewPanel) {
        this.panel = panel;
        this.panel.webview.html = this.getHtml();
        this.panel.onDidDispose(() => this.dispose(), null, this.disposables);
    }

    reset(task: string): void {
        this.postMessage({ type: 'RESET', task });
    }

    setPlan(steps: Array<{ step: number; tool: string; description: string; is_destructive?: boolean }>): void {
        this.postMessage({ type: 'PLAN', steps });
    }

    stepStart(step: number, description: string): void {
        this.postMessage({ type: 'STEP_START', step, description });
    }

    stepResult(step: number, payload: { success?: boolean; skipped?: boolean; result?: unknown; error?: string; reason?: string }): void {
        this.postMessage({ type: 'STEP_RESULT', step, payload });
    }

    log(text: string, tone: 'default' | 'good' | 'warn' | 'bad' = 'default'): void {
        this.postMessage({ type: 'LOG', text, tone });
    }

    complete(text: string): void {
        this.postMessage({ type: 'COMPLETE', text });
    }

    private postMessage(message: Record<string, unknown>): void {
        this.panel.webview.postMessage(message);
    }

    private getHtml(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    body { font-family: var(--vscode-font-family); background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); margin: 0; padding: 16px; }
    h1, h2, p { margin: 0; }
    .stack { display: flex; flex-direction: column; gap: 12px; }
    .card { border: 1px solid var(--vscode-panel-border); border-radius: 10px; background: var(--vscode-editorWidget-background); padding: 12px; }
    .muted { color: var(--vscode-descriptionForeground); font-size: 12px; }
    .step { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 10px; margin-top: 8px; }
    .step-title { font-size: 13px; font-weight: 600; }
    .step-meta { color: var(--vscode-descriptionForeground); font-size: 11px; margin-top: 4px; }
    .log { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 10px; font-size: 12px; white-space: pre-wrap; }
    .good { border-color: var(--vscode-testing-iconPassed, #3fb950); color: var(--vscode-testing-iconPassed, #3fb950); }
    .warn { border-color: var(--vscode-testing-iconQueued, #d29922); color: var(--vscode-testing-iconQueued, #d29922); }
    .bad { border-color: var(--vscode-errorForeground, #f85149); color: var(--vscode-errorForeground, #f85149); }
    pre { white-space: pre-wrap; font-size: 11px; margin: 8px 0 0 0; }
  </style>
</head>
<body>
  <div class="stack">
    <div class="card">
      <h1>System Agent</h1>
      <p id="task" class="muted">No task running.</p>
    </div>
    <div class="card">
      <h2>Plan</h2>
      <div id="plan" class="muted" style="margin-top: 8px;">Waiting for planner output.</div>
    </div>
    <div class="card">
      <h2>Activity</h2>
      <div id="activity" class="stack" style="margin-top: 8px;"></div>
    </div>
  </div>
  <script>
    const plan = document.getElementById('plan');
    const activity = document.getElementById('activity');
    const task = document.getElementById('task');

    function appendLog(text, tone = 'default') {
      const el = document.createElement('div');
      el.className = 'log ' + tone;
      el.textContent = text;
      activity.appendChild(el);
      el.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    function renderPlan(steps) {
      if (!steps || !steps.length) {
        plan.textContent = 'Planner returned no steps.';
        return;
      }
      plan.innerHTML = '';
      steps.forEach((step) => {
        const el = document.createElement('div');
        el.className = 'step';
        el.innerHTML = '<div class="step-title">' + step.step + '. ' + step.description + '</div>'
          + '<div class="step-meta">' + step.tool + (step.is_destructive ? ' • destructive' : '') + '</div>';
        plan.appendChild(el);
      });
    }

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'RESET') {
        task.textContent = msg.task || 'Running task...';
        plan.textContent = 'Waiting for planner output.';
        activity.innerHTML = '';
        return;
      }
      if (msg.type === 'PLAN') {
        renderPlan(msg.steps || []);
        return;
      }
      if (msg.type === 'STEP_START') {
        appendLog('Step ' + msg.step + ' started: ' + msg.description);
        return;
      }
      if (msg.type === 'STEP_RESULT') {
        const payload = msg.payload || {};
        const summary = payload.error || payload.reason || JSON.stringify(payload.result || {}, null, 2);
        appendLog('Step ' + msg.step + ' result:\\n' + summary, payload.success ? 'good' : payload.skipped ? 'warn' : 'default');
        return;
      }
      if (msg.type === 'LOG') {
        appendLog(msg.text || '', msg.tone || 'default');
        return;
      }
      if (msg.type === 'COMPLETE') {
        appendLog(msg.text || 'Task complete.', 'good');
      }
    });
  </script>
</body>
</html>`;
    }

    dispose(): void {
        SystemAgentPanel.currentPanel = undefined;
        this.panel.dispose();
        this.disposables.forEach((item) => item.dispose());
    }
}
