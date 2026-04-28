/**
 * JimAI Chrome extension background service worker.
 * Handles context menus, side panel, screenshots, and message routing.
 */

const DEFAULT_BACKEND = 'http://localhost:8000';
const SETTINGS_KEY = 'jimai_settings';

async function backendUrl(): Promise<string> {
    try {
        const result = await chrome.storage.local.get(SETTINGS_KEY);
        const stored = result[SETTINGS_KEY] as { backendUrl?: string } | undefined;
        const url = stored?.backendUrl || DEFAULT_BACKEND;
        return url.replace(/\/+$/, '');
    } catch {
        return DEFAULT_BACKEND;
    }
}

function csrfHeaders(): Record<string, string> {
    return { 'Content-Type': 'application/json', 'X-JimAI-CSRF': '1' };
}

chrome.runtime.onInstalled.addListener(() => {
    const menuItems = [
        { id: 'explain', title: 'JimAI · Explain this' },
        { id: 'solve', title: 'JimAI · Solve this' },
        { id: 'rewrite', title: 'JimAI · Rewrite this' },
        { id: 'summarize', title: 'JimAI · Summarize page' },
        { id: 'explain-stats', title: 'JimAI · Explain stats output' },
    ];

    for (const item of menuItems) {
        chrome.contextMenus.create({
            id: item.id,
            title: item.title,
            contexts: ['selection', 'page'],
        });
    }
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    const selectedText = info.selectionText || '';
    const id = String(info.menuItemId);

    const modeMap: Record<string, string> = {
        explain: 'chat', solve: 'math', rewrite: 'writing',
        summarize: 'chat', 'explain-stats': 'math',
    };
    const promptMap: Record<string, string> = {
        explain: `Explain this: ${selectedText}`,
        solve: `Solve this: ${selectedText}`,
        rewrite: `Rewrite this to be clearer and more concise: ${selectedText}`,
        summarize: `Summarize the following text: ${selectedText}`,
        'explain-stats': `Explain this statistical output in plain language. State the test, null hypothesis, result, and practical meaning:\n\n${selectedText}`,
    };
    const mode = modeMap[id] || 'chat';
    const prompt = promptMap[id] || selectedText;

    if (tab?.id) {
        try { await chrome.sidePanel.open({ tabId: tab.id }); } catch { /* ignore */ }
    }

    try {
        const base = await backendUrl();
        const response = await fetch(`${base}/api/chat`, {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({
                message: prompt, mode, session_id: 'extension', history: [],
            }),
        });

        const reader = response.body?.getReader();
        if (!reader) return;
        const decoder = new TextDecoder();
        let fullText = '';
        let buf = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) fullText += data.text;
                } catch { /* skip */ }
            }
        }

        chrome.runtime.sendMessage({ type: 'AI_RESPONSE', text: fullText, mode });
        if (tab?.id && selectedText) {
            chrome.tabs.sendMessage(tab.id, { type: 'ANNOTATE', text: fullText }).catch(() => {});
        }
    } catch (err) {
        console.error('JimAI: backend request failed:', err);
    }
});

chrome.action.onClicked.addListener(async (tab) => {
    if (tab.id) {
        try { await chrome.sidePanel.open({ tabId: tab.id }); } catch { /* ignore */ }
    }
});

chrome.commands.onCommand.addListener(async (command) => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (command === 'toggle-sidebar' && tab?.id) {
        try { await chrome.sidePanel.open({ tabId: tab.id }); } catch { /* ignore */ }
    }

    if (command === 'capture-screen' && tab?.id && tab.windowId) {
        try {
            const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
            const base64 = screenshot.replace('data:image/png;base64,', '');
            await chrome.sidePanel.open({ tabId: tab.id });
            setTimeout(() => {
                chrome.runtime.sendMessage({ type: 'SCREENSHOT_CAPTURED', image: base64 });
            }, 500);
        } catch (e) {
            console.warn('JimAI: could not capture tab:', e);
        }
    }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === 'INDEX_PAGE') {
        indexPage(message.url).then((result) => sendResponse(result));
        return true;
    }
    if (message?.type === 'SEND_VISION') {
        sendVision(message.image, message.prompt).then((result) => sendResponse(result));
        return true;
    }
    return false;
});

async function indexPage(url: string): Promise<{ success: boolean; error?: string }> {
    try {
        const base = await backendUrl();
        const resp = await fetch(`${base}/api/upload/url`, {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({ url, session_id: 'extension' }),
        });
        return await resp.json();
    } catch (err) {
        return { success: false, error: String(err) };
    }
}

async function sendVision(imageBase64: string, prompt: string): Promise<string> {
    try {
        const base = await backendUrl();
        const resp = await fetch(`${base}/api/vision`, {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({ image: imageBase64, prompt }),
        });
        const reader = resp.body?.getReader();
        if (!reader) return '';
        const decoder = new TextDecoder();
        let fullText = '';
        let buf = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop() || '';
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.text) fullText += data.text;
                } catch { /* skip */ }
            }
        }
        return fullText;
    } catch (err) {
        return `Error: ${err}`;
    }
}
