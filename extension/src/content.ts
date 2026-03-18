/**
 * Content script — injected into all pages.
 * Handles annotations, highlights, page capture, and auto-detection.
 */

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    switch (message.type) {
        case 'ANNOTATE':
            showAnnotation(message.text);
            sendResponse({ ok: true });
            break;
        case 'HIGHLIGHT':
            highlightSelection();
            sendResponse({ ok: true });
            break;
        case 'CAPTURE_REQUEST':
            sendResponse({ text: document.body.innerText });
            break;
        default:
            sendResponse({ ok: false });
    }
    return true;
});

function showAnnotation(text: string): void {
    const existing = document.getElementById('private-ai-annotation');
    if (existing) existing.remove();

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    const tooltip = document.createElement('div');
    tooltip.id = 'private-ai-annotation';
    tooltip.style.cssText = `
        position: fixed;
        top: ${rect.bottom + 8}px;
        left: ${Math.max(rect.left, 8)}px;
        max-width: 400px;
        max-height: 300px;
        overflow-y: auto;
        background: #111114;
        color: #e8e8f0;
        border: 1px solid #1e1e24;
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 13px;
        line-height: 1.5;
        box-shadow: 0 20px 60px rgba(0,0,0,0.6);
        z-index: 999999;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    `;

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = `position:absolute;top:4px;right:8px;background:none;border:none;color:#40405a;font-size:18px;cursor:pointer;padding:4px;`;
    closeBtn.onclick = () => tooltip.remove();

    const content = document.createElement('div');
    content.textContent = text;
    content.style.marginRight = '20px';

    tooltip.appendChild(closeBtn);
    tooltip.appendChild(content);
    document.body.appendChild(tooltip);

    setTimeout(() => {
        document.addEventListener('click', (e) => {
            if (!tooltip.contains(e.target as Node)) tooltip.remove();
        }, { once: true });
    }, 100);
}

function highlightSelection(): void {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;

    const range = selection.getRangeAt(0);
    const mark = document.createElement('mark');
    mark.setAttribute('data-private-ai', 'true');
    mark.style.cssText = `background:rgba(79,142,247,0.15);border-bottom:2px solid rgba(79,142,247,0.4);padding:0 2px;border-radius:2px;`;

    try {
        range.surroundContents(mark);
    } catch {
        console.warn('Could not highlight selection');
    }
}

// Auto-detection: check if this is an academic paper (arxiv, doi, etc.)
function detectAcademicPaper(): boolean {
    const url = window.location.href;
    const isAcademic = /arxiv\.org|doi\.org|scholar\.google|semanticscholar|pubmed/.test(url);
    const hasAbstract = !!document.querySelector('[class*="abstract"], #abstract, .abstract');
    return isAcademic || hasAbstract;
}

// Auto-detection: find code blocks on the page
function detectCodeBlocks(): HTMLElement[] {
    return Array.from(document.querySelectorAll('pre code, .highlight pre, .code-block')) as HTMLElement[];
}

// Inject buttons on page load
function injectAutoDetectFeatures() {
    if (detectAcademicPaper()) {
        const btn = document.createElement('div');
        btn.id = 'private-ai-index-paper';
        btn.innerHTML = '📚 Index this paper';
        btn.style.cssText = `
            position: fixed; bottom: 20px; right: 20px; z-index: 999998;
            background: #4f8ef7; color: white; padding: 8px 14px;
            border-radius: 6px; font-size: 13px; cursor: pointer;
            font-family: 'Inter', sans-serif; box-shadow: 0 4px 20px rgba(79,142,247,0.3);
        `;
        btn.onclick = () => {
            chrome.runtime.sendMessage({ type: 'INDEX_PAGE', url: window.location.href });
            btn.innerHTML = '✓ Indexed';
            btn.style.background = '#34d399';
            setTimeout(() => btn.remove(), 3000);
        };
        document.body.appendChild(btn);
    }

    const codeBlocks = detectCodeBlocks();
    codeBlocks.forEach((block) => {
        if (block.querySelector('.private-ai-explain-btn')) return;

        const btn = document.createElement('button');
        btn.className = 'private-ai-explain-btn';
        btn.textContent = 'Explain code';
        btn.style.cssText = `
            display: block; margin: 4px 0; padding: 3px 8px;
            background: #111114; color: #7070a0; border: 1px solid #1e1e24;
            border-radius: 4px; font-size: 11px; cursor: pointer;
            font-family: 'Inter', sans-serif;
        `;
        btn.onclick = () => {
            const code = block.textContent || '';
            chrome.runtime.sendMessage({
                type: 'AI_RESPONSE',
                text: '',
                mode: 'code',
            });
            // Use context menu approach for the actual explanation
            fetch('http://localhost:8000/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: `Explain this code:\n\n${code.slice(0, 3000)}`,
                    mode: 'code',
                    session_id: 'extension',
                    history: [],
                }),
            }).then(async (resp) => {
                const reader = resp.body?.getReader();
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
                showAnnotation(fullText);
            });
        };
        block.parentElement?.insertBefore(btn, block);
    });
}

// Run detection after page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(injectAutoDetectFeatures, 1000));
} else {
    setTimeout(injectAutoDetectFeatures, 1000);
}
