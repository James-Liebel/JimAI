const { spawn } = require('child_process');
const path = require('path');
const { app, BrowserWindow, Menu, shell } = require('electron');

const DEFAULT_UI_URL = process.env.AGENTSPACE_UI_URL || 'http://localhost:5173';
const ALLOW_DEVTOOLS = process.env.AGENTSPACE_DEVTOOLS === '1';
const REPO_ROOT = path.resolve(__dirname, '..');
const PYTHON_BIN = process.env.AGENTSPACE_PYTHON || 'python';
const AUTO_STOP_SERVICES = process.env.AGENTSPACE_AUTO_STOP === '1';

let mainWindow = null;
let stopRequested = false;
let reloadInFlight = false;

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
    let uiOrigin = 'http://localhost:5173';
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
            sandbox: true,
            webSecurity: true,
            allowRunningInsecureContent: false,
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
