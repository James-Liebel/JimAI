const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const { app, BrowserWindow, Menu, shell } = require('electron');

// 127.0.0.1 avoids Windows resolving "localhost" to ::1 while Vite is IPv4-only.
const DEFAULT_UI_URL = process.env.AGENTSPACE_UI_URL || 'http://127.0.0.1:5173';
const ALLOW_DEVTOOLS = process.env.AGENTSPACE_DEVTOOLS === '1';
const REPO_ROOT = path.resolve(__dirname, '..');
const PYTHON_BIN = process.env.AGENTSPACE_PYTHON || 'python';
const AUTO_STOP_SERVICES = process.env.AGENTSPACE_AUTO_STOP === '1';

let mainWindow = null;
let stopRequested = false;
let reloadInFlight = false;

// Keep GPU free for AI inference — the UI is text-heavy and renders fine on CPU.
app.disableHardwareAcceleration();

const gotSingleInstanceLock = app.requestSingleInstanceLock();

function isTrustedAppUrl(url, allowedOrigin) {
    try {
        const parsed = new URL(url);
        return parsed.origin === allowedOrigin;
    } catch {
        return false;
    }
}

function requestStopOnQuit() {
    if (!AUTO_STOP_SERVICES || stopRequested) return;
    stopRequested = true;
    try {
        const stopHelper = spawn(PYTHON_BIN, ['scripts/agentspace_lifecycle.py', 'stop'], {
            cwd: REPO_ROOT,
            detached: true,
            stdio: 'ignore',
            windowsHide: true,
            env: {
                ...process.env,
                AGENTSPACE_AUTO_STOP: '0',
            },
        });
        stopHelper.unref();
    } catch (error) {
        console.error('Failed to stop JimAI services on close:', error);
    }
}

function buildUnavailableHtml(message) {
    return `
        <html>
        <head>
            <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:;">
        </head>
        <body style="font-family: Segoe UI, sans-serif; background:#0b1020; color:#e6edf7; padding:24px;">
            <h2>jimAI UI is not running</h2>
            <p>${message}</p>
            <p>Expected URL: ${DEFAULT_UI_URL}</p>
        </body>
        </html>
    `;
}

async function showUnavailablePage(window, message) {
    if (window.isDestroyed()) return;
    const html = buildUnavailableHtml(message);
    await window.loadURL(`data:text/html,${encodeURIComponent(html)}`);
}

function probeUiReachable(urlString) {
    return new Promise((resolve) => {
        let u;
        try {
            u = new URL(urlString);
        } catch {
            resolve(false);
            return;
        }
        if (u.protocol !== 'http:' && u.protocol !== 'https:') {
            resolve(false);
            return;
        }
        const mod = u.protocol === 'https:' ? require('https') : http;
        const port = u.port || (u.protocol === 'https:' ? '443' : '80');
        const req = mod.request(
            {
                hostname: u.hostname,
                port,
                path: u.pathname || '/',
                method: 'GET',
                timeout: 2500,
            },
            (res) => {
                res.resume();
                resolve(res.statusCode != null && res.statusCode < 500);
            },
        );
        req.on('error', () => resolve(false));
        req.on('timeout', () => {
            req.destroy();
            resolve(false);
        });
        req.end();
    });
}

async function waitForUiReady(urlString, maxWaitMs = 90000) {
    const deadline = Date.now() + maxWaitMs;
    while (Date.now() < deadline) {
        if (await probeUiReachable(urlString)) return true;
        await new Promise((r) => setTimeout(r, 400));
    }
    return false;
}

async function showWaitingPage(window) {
    if (window.isDestroyed()) return;
    const html = `
        <html><head><meta charset="utf-8">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
        </head>
        <body style="font-family: Segoe UI, sans-serif; background:#0b1020; color:#e6edf7; padding:24px;">
        <h2>jimAI</h2>
        <p>Starting the UI server… This can take a minute the first time.</p>
        <p style="opacity:0.8;font-size:14px;">${DEFAULT_UI_URL}</p>
        </body></html>`;
    await window.loadURL(`data:text/html,${encodeURIComponent(html)}`);
}

async function loadUi(window, { ignoreCache = false } = {}) {
    if (!window || window.isDestroyed()) return;
    if (reloadInFlight) return;
    reloadInFlight = true;
    try {
        if (ignoreCache) {
            try {
                await window.webContents.session.clearCache();
            } catch {}
        }
        await showWaitingPage(window);
        const ready = await waitForUiReady(DEFAULT_UI_URL);
        if (!ready) {
            await showUnavailablePage(
                window,
                'The UI server did not become ready in time. Use jimai / Open JimAI.cmd to start services, or Reload from the menu.',
            );
            return;
        }
        await window.loadURL(DEFAULT_UI_URL);
    } catch {
        await showUnavailablePage(window, 'Start backend + frontend first, then reload this window.');
    } finally {
        reloadInFlight = false;
    }
}

function createWindow() {
    if (mainWindow && !mainWindow.isDestroyed()) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
        void loadUi(mainWindow);
        return mainWindow;
    }
    let uiOrigin = 'http://127.0.0.1:5173';
    try {
        uiOrigin = new URL(DEFAULT_UI_URL).origin;
    } catch {}
    const window = new BrowserWindow({
        width: 1440,
        height: 920,
        minWidth: 1024,
        minHeight: 700,
        title: 'jimAI',
        autoHideMenuBar: false,
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            // Vite dev + React Refresh rely on patterns that break in a sandboxed renderer (blank white window).
            sandbox: false,
            webSecurity: true,
            allowRunningInsecureContent: false,
            // Required for <webview> tag used by Atlas browser tab.
            webviewTag: true,
        },
    });
    mainWindow = window;

    window.on('closed', () => {
        if (mainWindow === window) {
            mainWindow = null;
        }
    });

    window.webContents.setWindowOpenHandler(({ url }) => {
        if (isTrustedAppUrl(url, uiOrigin)) return { action: 'allow' };
        shell.openExternal(url);
        return { action: 'deny' };
    });

    window.webContents.on('will-navigate', (event, url) => {
        if (isTrustedAppUrl(url, uiOrigin)) return;
        event.preventDefault();
        if (url && url !== 'about:blank') shell.openExternal(url);
    });

    window.webContents.on('before-input-event', (event, input) => {
        const key = String(input.key || '').toLowerCase();
        const wantsReload = key === 'f5' || ((input.control || input.meta) && key === 'r');
        if (!wantsReload) return;
        event.preventDefault();
        const ignoreCache = key === 'f5' || Boolean(input.shift);
        void loadUi(window, { ignoreCache });
    });

    const template = [
        {
            label: 'jimAI',
            submenu: [
                {
                    label: 'Open In Browser',
                    click: () => shell.openExternal(DEFAULT_UI_URL),
                },
                { type: 'separator' },
                {
                    label: 'Reload UI',
                    accelerator: 'CmdOrCtrl+R',
                    click: () => {
                        void loadUi(window);
                    },
                },
                {
                    label: 'Hard Reload UI',
                    accelerator: 'CmdOrCtrl+Shift+R',
                    click: () => {
                        void loadUi(window, { ignoreCache: true });
                    },
                },
                ...(ALLOW_DEVTOOLS ? [{ role: 'toggleDevTools' }] : []),
                { type: 'separator' },
                { role: 'quit' },
            ],
        },
        {
            label: 'Edit',
            submenu: [{ role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }],
        },
        {
            label: 'View',
            submenu: [{ role: 'togglefullscreen' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }],
        },
    ];
    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);

    window.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
        if (!isMainFrame) return;
        if (errorCode === -3) return;
        if (!validatedURL || validatedURL.startsWith('data:')) return;
        void showUnavailablePage(window, `Reload failed: ${errorDescription || `error ${errorCode}`}.`);
    });

    window.webContents.on('render-process-gone', () => {
        void showUnavailablePage(window, 'The UI process exited. Reload the window to reconnect.');
    });

    void loadUi(window);

    return window;
}

if (!gotSingleInstanceLock) {
    app.quit();
} else {
    app.on('second-instance', () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
            void loadUi(mainWindow, { ignoreCache: true });
            return;
        }
        if (app.isReady()) {
            createWindow();
        }
    });

    app.whenReady().then(createWindow);

    app.on('activate', () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.focus();
            void loadUi(mainWindow);
            return;
        }
        createWindow();
    });

    app.on('before-quit', () => {
        requestStopOnQuit();
    });

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') app.quit();
    });
}
