/**
 * Chrome extension background service worker.
 * Handles context menus, side panel, screenshots, and message routing.
 */

const BACKEND_URL = 'http://localhost:8000';

chrome.runtime.onInstalled.addListener(() => {
    const menuItems = [
        { id: 'explain', title: 'Explain this' },
        { id: 'solve', title: 'Solve this' },
        { id: 'rewrite', title: 'Rewrite this' },
        { id: 'summarize', title: 'Summarize page' },
        { id: 'explain-stats', title: 'Explain stats output' },
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

    const modeMap: Record<string, string> = {
        explain: 'chat',
        solve: 'math',
        rewrite: 'writing',
        summarize: 'chat',
        'explain-stats': 'math',
    };

    const promptMap: Record<string, string> = {
        explain: `Explain this: ${selectedText}`,
        solve: `Solve this: ${selectedText}`,
        rewrite: `Rewrite this to be clearer and more concise: ${selectedText}`,
        summarize: `Summarize the following text: ${selectedText}`,
        'explain-stats': `Explain this statistical output in plain language. State the test, null hypothesis, result, and practical meaning:\n\n${selectedText}`,
    };

    const mode = modeMap[info.menuItemId as string] || 'chat';
    const prompt = promptMap[info.menuItemId as string] || selectedText;

    try {
        const response = await fetch(`${BACKEND_URL}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: prompt,
                mode,
                session_id: 'extension',
                history: [],
            }),
        });

        const reader = response.body?.getReader();
        if (!reader) return;

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

        chrome.runtime.sendMessage({ type: 'AI_RESPONSE', text: fullText, mode });

        if (tab?.id && selectedText) {
            chrome.tabs.sendMessage(tab.id, { type: 'ANNOTATE', text: fullText });
        }
    } catch (err) {
        console.error('Backend request failed:', err);
    }
});

// Extension icon click → open side panel
chrome.action.onClicked.addListener(async (tab) => {
    if (tab.id) {
        await chrome.sidePanel.open({ tabId: tab.id });
    }
});

// Keyboard commands
chrome.commands.onCommand.addListener(async (command) => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (command === 'toggle-sidebar') {
        if (tab?.id) {
            await chrome.sidePanel.open({ tabId: tab.id });
        }
    }

    if (command === 'capture-screen') {
        if (tab?.id && tab.windowId) {
            try {
                const screenshot = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
                const base64 = screenshot.replace('data:image/png;base64,', '');

                await chrome.sidePanel.open({ tabId: tab.id });

                // Send screenshot to sidebar with a short delay to let it render
                setTimeout(() => {
                    chrome.runtime.sendMessage({
                        type: 'SCREENSHOT_CAPTURED',
                        image: base64,
                    });
                }, 500);
            } catch (e) {
                console.warn('Could not capture tab:', e);
            }
        }
    }
});

// Handle messages from content script and sidebar
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === 'INDEX_PAGE') {
        indexPage(message.url).then((result) => sendResponse(result));
        return true;
    }
    if (message.type === 'SEND_VISION') {
        sendVision(message.image, message.prompt).then((result) => sendResponse(result));
        return true;
    }
});

async function indexPage(url: string) {
    try {
        const resp = await fetch(`${BACKEND_URL}/api/upload/url`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, session_id: 'extension' }),
        });
        return await resp.json();
    } catch (err) {
        return { success: false, error: String(err) };
    }
}

async function sendVision(imageBase64: string, prompt: string): Promise<string> {
    try {
        const resp = await fetch(`${BACKEND_URL}/api/vision`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: imageBase64, prompt }),
        });

        const reader = resp.body?.getReader();
        if (!reader) return '';

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
    } catch (err) {
        return `Error: ${err}`;
    }
}
