const { app, BrowserWindow, Menu, shell } = require('electron');

const DEFAULT_UI_URL = process.env.AGENTSPACE_UI_URL || 'http://localhost:5173';
const ALLOW_DEVTOOLS = process.env.AGENTSPACE_DEVTOOLS === '1';

function isTrustedAppUrl(url, allowedOrigin) {
    try {
        const parsed = new URL(url);
        return parsed.origin === allowedOrigin;
    } catch {
        return false;
    }
}

function createWindow() {
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

    const template = [
        {
            label: 'jimAI',
            submenu: [
                {
                    label: 'Open In Browser',
                    click: () => shell.openExternal(DEFAULT_UI_URL),
                },
                { type: 'separator' },
                { role: 'reload' },
                { role: 'forceReload' },
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

    window.loadURL(DEFAULT_UI_URL).catch(() => {
        const html = `
            <html>
            <head>
                <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:;">
            </head>
            <body style="font-family: Segoe UI, sans-serif; background:#0b1020; color:#e6edf7; padding:24px;">
                <h2>jimAI UI is not running</h2>
                <p>Start backend + frontend first, then reload this window.</p>
                <p>Expected URL: ${DEFAULT_UI_URL}</p>
            </body>
            </html>
        `;
        window.loadURL(`data:text/html,${encodeURIComponent(html)}`);
    });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
