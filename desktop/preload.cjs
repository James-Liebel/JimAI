// Preload script for the main JimAI window. Exposes a narrow, vetted bridge so
// the renderer (BrowserAtlas.tsx) can ask the main process to perform actions
// that require privileged APIs:
//   • uploadToWebview — attach a file to an <input type=file> inside a <webview>
//     via Chrome DevTools Protocol (DOM.setFileInputFiles). The renderer alone
//     can't construct File objects from arbitrary disk paths because of the
//     web platform's security model.
//   • listDownloads — list files the atlas session has downloaded since launch.
//
// contextIsolation is enabled so we go through contextBridge; nothing on the
// Electron API surface leaks into the page itself.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jimaiBridge', {
    uploadToWebview: (webContentsId, selector, paths) =>
        ipcRenderer.invoke('atlas:upload-to-webview', { webContentsId, selector, paths }),
    listDownloads: () => ipcRenderer.invoke('atlas:list-downloads'),
    readDownload: (filename, maxBytes) =>
        ipcRenderer.invoke('atlas:read-download', { filename, maxBytes }),
    // Save the webview's current page as PDF into the Atlas downloads sandbox.
    saveWebviewPdf: (webContentsId, filename) =>
        ipcRenderer.invoke('atlas:save-webview-pdf', { webContentsId, filename }),
    // Pierce open *and closed* shadow roots via CDP — the renderer's JS cannot
    // see closed shadow DOM, but the debugger protocol can.
    indexWithCdp: (webContentsId) =>
        ipcRenderer.invoke('atlas:cdp-index', { webContentsId }),
});
