import * as vscode from 'vscode';

async function streamChatToOutput(backendUrl: string, message: string, mode: string): Promise<string> {
    const resp = await fetch(`${backendUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, mode, session_id: 'vscode-ds', history: [] }),
    });

    if (!resp.body) return '';
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        for (const line of text.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            try {
                const data = JSON.parse(line.slice(6));
                if (data.text) fullText += data.text;
            } catch { /* skip */ }
        }
    }
    return fullText;
}

export async function profileDataset(backendUrl: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('Open a CSV file first');
        return;
    }

    if (!editor.document.fileName.endsWith('.csv')) {
        vscode.window.showWarningMessage('Profile Dataset only works on CSV files');
        return;
    }

    const content = editor.document.getText();
    const first1000 = content.split('\n').slice(0, 50).join('\n');

    const channel = vscode.window.createOutputChannel('Private AI - Dataset Profile');
    channel.show();
    channel.appendLine('Profiling dataset...\n');

    const result = await streamChatToOutput(
        backendUrl,
        `Profile this CSV dataset. Show shape, dtypes, missing values, basic stats, and notable patterns:\n\n${first1000}`,
        'code',
    );
    channel.appendLine(result);
}

export async function suggestMLModel(backendUrl: string): Promise<void> {
    const description = await vscode.window.showInputBox({
        prompt: 'Describe your ML task',
        placeHolder: 'e.g., Predict house prices from 20 features, 10k rows, mix of numeric and categorical',
    });

    if (!description) return;

    const channel = vscode.window.createOutputChannel('Private AI - ML Suggestion');
    channel.show();
    channel.appendLine('Analyzing task...\n');

    const result = await streamChatToOutput(
        backendUrl,
        `Suggest the best ML model for this task: ${description}\n\nInclude: recommended algorithm, why, hyperparameters to tune, evaluation metrics, and a sklearn code template.`,
        'code',
    );
    channel.appendLine(result);
}

export async function explainStatsOutput(backendUrl: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const selection = editor.document.getText(editor.selection);
    if (!selection) {
        vscode.window.showWarningMessage('Select the statistical output to explain');
        return;
    }

    const channel = vscode.window.createOutputChannel('Private AI - Stats Explanation');
    channel.show();
    channel.appendLine('Analyzing statistical output...\n');

    const result = await streamChatToOutput(
        backendUrl,
        `Explain this statistical output in plain language. State what the test is, the null hypothesis, the result, and what it means practically:\n\n${selection}`,
        'math',
    );
    channel.appendLine(result);
}

export async function generateEDA(backendUrl: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('Open a CSV file first');
        return;
    }

    const content = editor.document.getText();
    const first500 = content.split('\n').slice(0, 30).join('\n');

    const channel = vscode.window.createOutputChannel('Private AI - EDA');
    channel.show();
    channel.appendLine('Generating EDA notebook...\n');

    const result = await streamChatToOutput(
        backendUrl,
        `Generate a complete EDA (Exploratory Data Analysis) Python notebook for this CSV data. Include: data loading, shape/dtypes, missing values analysis, univariate distributions, bivariate correlations, outlier detection, and summary. Use pandas, matplotlib, seaborn.\n\nFirst rows of the data:\n${first500}`,
        'code',
    );
    channel.appendLine(result);
}
