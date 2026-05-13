const { spawn, execSync } = require('child_process');
const http = require('http');
const net = require('net');
const path = require('path');
const fs = require('fs');
const { app, BrowserWindow, Menu, shell, session } = require('electron');

// 127.0.0.1 avoids Windows resolving "localhost" to ::1 while Vite is IPv4-only.
const DEFAULT_UI_URL = process.env.AGENTSPACE_UI_URL || 'http://127.0.0.1:5173';
const BACKEND_URL = process.env.AGENTSPACE_BACKEND_URL || 'http://127.0.0.1:8000';
const BACKEND_HEALTH_URL = `${BACKEND_URL}/health`;
const ALLOW_DEVTOOLS = process.env.AGENTSPACE_DEVTOOLS === '1';
const REPO_ROOT = path.resolve(__dirname, '..');
const PYTHON_BIN = process.env.AGENTSPACE_PYTHON || 'python';
const AUTO_STOP_SERVICES = process.env.AGENTSPACE_AUTO_STOP === '1';
// JIMAI_MANAGE_SERVICES=1 — Electron itself spawns backend + frontend and
// terminates them on quit. Used by the top-level "Start JimAI.cmd" launcher
// so closing the window ends every process tree we created.
const MANAGE_SERVICES = process.env.JIMAI_MANAGE_SERVICES === '1';
const BACKEND_PORT = Number(process.env.JIMAI_BACKEND_PORT || 8000);
const FRONTEND_PORT = Number(process.env.JIMAI_FRONTEND_PORT || 5173);
const OLLAMA_PORT = Number(process.env.JIMAI_OLLAMA_PORT || 11434);

let mainWindow = null;
let stopRequested = false;
let reloadInFlight = false;
// Track services we started so we can kill them in the right order on quit.
// Each entry: { name, child, killed }
const managedServices = [];

// Keep GPU free for AI inference — the UI is text-heavy and renders fine on CPU.
app.disableHardwareAcceleration();

// Atlas browser tab lives in <webview partition="persist:atlas">. Google's
// sign-in "secure browser" check rejects any UA that looks like an embedded
// browser ("Couldn't sign you in — this browser may not be secure"). To pass:
//   1. Use a fully-formed desktop Chrome UA (not just an Electron-stripped one).
//   2. Send matching Sec-CH-UA / Sec-CH-UA-Platform client hints — Google reads
//      these and will reject if the brand list contains "Electron".
//   3. Drop "X-Requested-With" (browsers don't send it; some sites use it as a
//      bot signal).
//   4. Allow permissions a normal browser would prompt for (notifications,
//      clipboard, media) so logged-in sites that require them work.
// We also pre-create the session before any webview mounts so cookies persist
// on first run.
const ATLAS_PARTITION = 'persist:atlas';

function buildChromeUserAgent() {
    // Pin to whatever Chromium version Electron is shipping — that way Sec-CH-UA
    // and the UA string are consistent and we don't have to bump strings on Electron upgrades.
    const chromeVer = (process.versions && process.versions.chrome) || '134.0.0.0';
    const major = String(chromeVer).split('.')[0] || '134';
    let platformTag = 'Windows NT 10.0; Win64; x64';
    if (process.platform === 'darwin') platformTag = 'Macintosh; Intel Mac OS X 10_15_7';
    else if (process.platform === 'linux') platformTag = 'X11; Linux x86_64';
    return {
        ua: `Mozilla/5.0 (${platformTag}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${chromeVer} Safari/537.36`,
        major,
    };
}

function buildClientHints(major) {
    const platform =
        process.platform === 'darwin' ? '"macOS"' :
        process.platform === 'linux' ? '"Linux"' : '"Windows"';
    // Match Chrome's GREASE'd brand list format. Critically: no "Electron" entry.
    return {
        secChUa: `"Chromium";v="${major}", "Not(A:Brand";v="24", "Google Chrome";v="${major}"`,
        secChUaMobile: '?0',
        secChUaPlatform: platform,
    };
}

let atlasSessionRef = null;

function configureAtlasSession() {
    try {
        const atlasSession = session.fromPartition(ATLAS_PARTITION);
        atlasSessionRef = atlasSession;
        const { ua, major } = buildChromeUserAgent();
        const hints = buildClientHints(major);
        atlasSession.setUserAgent(ua);

        // Rewrite outgoing headers so embedded-browser fingerprints don't leak
        // and client hints match the spoofed UA.
        atlasSession.webRequest.onBeforeSendHeaders((details, callback) => {
            const headers = { ...details.requestHeaders };
            // Some bundlers / fetch wrappers send this — never present from a real Chrome.
            delete headers['X-Requested-With'];
            delete headers['x-requested-with'];
            // Force UA on every request even if a renderer overrode it locally.
            headers['User-Agent'] = ua;
            headers['Sec-Ch-Ua'] = hints.secChUa;
            headers['Sec-Ch-Ua-Mobile'] = hints.secChUaMobile;
            headers['Sec-Ch-Ua-Platform'] = hints.secChUaPlatform;
            callback({ requestHeaders: headers });
        });

        // Grant permissions a normal browser would prompt for (notifications,
        // clipboard, microphone/camera, geolocation, etc.). Without this many
        // logged-in sites silently break or show endless permission banners.
        atlasSession.setPermissionRequestHandler((_wc, _permission, cb) => cb(true));
        atlasSession.setPermissionCheckHandler(() => true);

        // Strip frame ancestors / X-Frame-Options on incoming responses so the
        // webview can host sites that would otherwise refuse to embed. Google's
        // OAuth flows already work in a top-level webview, but other identity
        // providers (Microsoft, Okta, etc.) sometimes do not.
        atlasSession.webRequest.onHeadersReceived((details, callback) => {
            const headers = { ...(details.responseHeaders || {}) };
            for (const key of Object.keys(headers)) {
                const lower = key.toLowerCase();
                if (lower === 'x-frame-options' || lower === 'content-security-policy') {
                    delete headers[key];
                }
            }
            callback({ responseHeaders: headers });
        });
    } catch (err) {
        console.error('[atlas] failed to configure session:', err);
    }
}

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

// ----- Self-managed service lifecycle (JIMAI_MANAGE_SERVICES=1) ----------

function isPortListening(port) {
    return new Promise((resolve) => {
        const sock = net.createConnection({ host: '127.0.0.1', port }, () => {
            sock.destroy();
            resolve(true);
        });
        sock.on('error', () => {
            resolve(false);
        });
        sock.setTimeout(800, () => {
            sock.destroy();
            resolve(false);
        });
    });
}

async function waitForPort(port, deadlineMs) {
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
        if (await isPortListening(port)) return true;
        await new Promise((r) => setTimeout(r, 500));
    }
    return false;
}

function spawnService({ name, command, args, cwd, env, logFile }) {
    const stdoutFd = logFile
        ? fs.openSync(logFile, 'a')
        : 'ignore';
    const stderrFd = logFile
        ? fs.openSync(logFile, 'a')
        : 'ignore';
    const child = spawn(command, args, {
        cwd,
        env: { ...process.env, ...(env || {}) },
        // detached:false on Windows so killing the process group via taskkill works.
        detached: false,
        windowsHide: true,
        stdio: ['ignore', stdoutFd, stderrFd],
    });
    const entry = { name, child, killed: false };
    managedServices.push(entry);
    child.on('exit', (code, signal) => {
        entry.killed = true;
        console.log(`[${name}] exited code=${code} signal=${signal}`);
    });
    child.on('error', (err) => {
        console.error(`[${name}] spawn error:`, err);
    });
    return entry;
}

function findOllamaExe() {
    if (process.platform !== 'win32') return 'ollama';
    // Prefer PATH so the user's chosen ollama install wins.
    try {
        const out = execSync('where ollama', { encoding: 'utf8', windowsHide: true }).trim();
        const first = out.split(/\r?\n/)[0].trim();
        if (first && fs.existsSync(first)) return first;
    } catch {
        // not on PATH — fall through to default install location
    }
    const localApp = process.env.LOCALAPPDATA;
    if (localApp) {
        const candidate = path.join(localApp, 'Programs', 'Ollama', 'ollama.exe');
        if (fs.existsSync(candidate)) return candidate;
    }
    return null;
}

async function maybeStartOllama(logsDir) {
    if (await isPortListening(OLLAMA_PORT)) {
        // Already running (e.g. user launched the Ollama tray app). Don't spawn,
        // and crucially don't track it in managedServices so we don't kill an
        // instance the user owns when Electron quits.
        console.log('[launcher] ollama already running on', OLLAMA_PORT, '— not spawning');
        return;
    }
    const exe = findOllamaExe();
    if (!exe) {
        console.log('[launcher] ollama not found on PATH — local-model features will be unavailable');
        return;
    }
    console.log('[launcher] starting ollama on', OLLAMA_PORT);
    spawnService({
        name: 'ollama',
        command: exe,
        args: ['serve'],
        cwd: REPO_ROOT,
        // Push more model layers onto the GPU and shrink the KV cache so less
        // work falls back to CPU (which is what's heating the laptop). Both
        // are safe defaults on Ollama 0.3+; KV cache quantization requires
        // flash attention, hence the pair.
        env: {
            OLLAMA_FLASH_ATTENTION: process.env.OLLAMA_FLASH_ATTENTION || '1',
            OLLAMA_KV_CACHE_TYPE: process.env.OLLAMA_KV_CACHE_TYPE || 'q8_0',
        },
        logFile: path.join(logsDir, 'ollama.log'),
    });
}

async function startManagedServices() {
    if (!MANAGE_SERVICES) return;
    const logsDir = path.join(REPO_ROOT, 'data', 'agent_space', 'logs', 'launcher');
    try {
        fs.mkdirSync(logsDir, { recursive: true });
    } catch {}

    // Ollama first — backend health checks call it on startup, so race-free
    // ordering matters. If we spawned it, stopManagedServices() will taskkill
    // /T it (and any model-runner child processes) on quit.
    await maybeStartOllama(logsDir);

    // Backend (uvicorn) — only if port 8000 is not already serving JimAI.
    const backendUp = await isPortListening(BACKEND_PORT);
    if (!backendUp) {
        console.log('[launcher] starting backend on port', BACKEND_PORT);
        spawnService({
            name: 'backend',
            command: PYTHON_BIN,
            args: [
                '-m', 'uvicorn', 'main:app',
                '--host', '127.0.0.1',
                '--port', String(BACKEND_PORT),
                '--log-level', 'info',
            ],
            cwd: path.join(REPO_ROOT, 'backend'),
            logFile: path.join(logsDir, 'backend.log'),
        });
    } else {
        console.log('[launcher] backend already responding on', BACKEND_PORT, '— not spawning');
    }

    // Frontend (vite) — only if port 5173 is not already serving.
    const frontendUp = await isPortListening(FRONTEND_PORT);
    if (!frontendUp) {
        console.log('[launcher] starting frontend on port', FRONTEND_PORT);
        const nodeBin = process.execPath; // electron's own node — vite runs via JS, not bin shim
        // Use a real node executable if available; fall back to system node.
        const systemNode = process.env.NODE_BINARY || 'node';
        spawnService({
            name: 'frontend',
            command: systemNode,
            args: [path.join('scripts', 'start_frontend_dev.mjs')],
            cwd: REPO_ROOT,
            env: {
                FRONTEND_HOST: '127.0.0.1',
                FRONTEND_PORT: String(FRONTEND_PORT),
            },
            logFile: path.join(logsDir, 'frontend.log'),
        });
    } else {
        console.log('[launcher] frontend already responding on', FRONTEND_PORT, '— not spawning');
    }
}

function killManagedService(entry, { force = false } = {}) {
    if (!entry || entry.killed || !entry.child || !entry.child.pid) return;
    const pid = entry.child.pid;
    try {
        if (process.platform === 'win32') {
            // taskkill /T kills the entire process tree (uvicorn + node + workers).
            const args = ['/PID', String(pid), '/T'];
            if (force) args.push('/F');
            spawn('taskkill', args, { windowsHide: true, stdio: 'ignore' });
        } else {
            entry.child.kill(force ? 'SIGKILL' : 'SIGTERM');
        }
    } catch (err) {
        console.error(`[${entry.name}] kill error:`, err);
    }
}

function stopManagedServices() {
    if (!MANAGE_SERVICES) return;
    if (managedServices.length === 0) return;
    console.log('[launcher] stopping', managedServices.length, 'managed service(s)');
    // First pass: graceful TERM.
    for (const entry of managedServices) killManagedService(entry, { force: false });
    // Hard kill any survivors after a short grace period.
    setTimeout(() => {
        for (const entry of managedServices) {
            if (!entry.killed) killManagedService(entry, { force: true });
        }
    }, 2500);
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

    // Atlas webview popups (e.g. Google's "Sign in with Google" OAuth window)
    // must stay in the same partition so cookies/auth state apply. By default
    // Electron's window-open handler in the main UI rejects external URLs and
    // sends them to the OS browser, which breaks the OAuth round-trip. Here we
    // catch contents created for the Atlas partition and route popups into a
    // new BrowserWindow that shares the same partition.
    app.on('web-contents-created', (_event, contents) => {
        try {
            if (contents.getType && contents.getType() !== 'webview') return;
            const sess = contents.session;
            if (!sess || sess !== atlasSessionRef) return;
            contents.setWindowOpenHandler(({ url }) => ({
                action: 'allow',
                overrideBrowserWindowOptions: {
                    width: 520,
                    height: 720,
                    title: 'Sign in',
                    webPreferences: {
                        contextIsolation: true,
                        nodeIntegration: false,
                        sandbox: false,
                        partition: ATLAS_PARTITION,
                    },
                },
            }));
            // Once a popup window opens, make sure its own popups follow the same rule.
            contents.on('did-create-window', (childWindow) => {
                childWindow.webContents.setWindowOpenHandler(({ url: childUrl }) => ({
                    action: 'allow',
                    overrideBrowserWindowOptions: {
                        webPreferences: {
                            contextIsolation: true,
                            nodeIntegration: false,
                            sandbox: false,
                            partition: ATLAS_PARTITION,
                        },
                    },
                }));
            });
        } catch (err) {
            console.error('[atlas] failed to wire popup handler:', err);
        }
    });

    app.whenReady().then(async () => {
        configureAtlasSession();
        // If the launcher set JIMAI_MANAGE_SERVICES=1, spawn backend + frontend
        // ourselves before opening the window, so closing the window kills the
        // whole stack via stopManagedServices().
        try {
            await startManagedServices();
        } catch (err) {
            console.error('[launcher] failed to start managed services:', err);
        }
        createWindow();
    });

    app.on('activate', () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.focus();
            void loadUi(mainWindow);
            return;
        }
        createWindow();
    });

    app.on('before-quit', () => {
        // Two cleanup paths exist intentionally:
        //   - AGENTSPACE_AUTO_STOP=1: defer to scripts/agentspace_lifecycle.py stop
        //     (used by the older 'Open JimAI.cmd' launcher)
        //   - JIMAI_MANAGE_SERVICES=1: kill the children we spawned in this process
        requestStopOnQuit();
        stopManagedServices();
    });

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') app.quit();
    });
}
