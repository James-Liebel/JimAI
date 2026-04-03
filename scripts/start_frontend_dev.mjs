import { fileURLToPath } from 'node:url';
import path from 'path';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, '..', 'frontend');
const viteEntry = path.resolve(root, 'node_modules', 'vite', 'dist', 'node', 'index.js');
const { createServer } = await import(`file:///${viteEntry.replace(/\\/g, '/')}`);

const host = process.env.FRONTEND_HOST || process.env.HOST || '0.0.0.0';
const port = Number(process.env.FRONTEND_PORT || 5173);

// Use frontend/vite.config.mjs (single source of truth). Avoid inline config with
// optimizeDeps.disabled — removed in Vite 5.1+ and caused blank Electron windows.
const server = await createServer({
    root,
    configFile: path.resolve(root, 'vite.config.mjs'),
    clearScreen: false,
    server: {
        host,
        port,
        strictPort: true,
    },
});

await server.listen();
server.printUrls();

const closeServer = async () => {
    try {
        await server.close();
    } finally {
        process.exit(0);
    }
};

process.on('SIGINT', () => {
    void closeServer();
});

process.on('SIGTERM', () => {
    void closeServer();
});
