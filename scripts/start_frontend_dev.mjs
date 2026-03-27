import { fileURLToPath } from 'node:url';
import path from 'node:path';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, '..', 'frontend');
const viteEntry = path.resolve(root, 'node_modules', 'vite', 'dist', 'node', 'index.js');
const reactPluginEntry = path.resolve(root, 'node_modules', '@vitejs', 'plugin-react', 'dist', 'index.js');
const { createServer } = await import(`file:///${viteEntry.replace(/\\/g, '/')}`);
const reactPluginModule = await import(`file:///${reactPluginEntry.replace(/\\/g, '/')}`);
const react = reactPluginModule.default;
const host = process.env.FRONTEND_HOST || process.env.HOST || '0.0.0.0';
const port = Number(process.env.FRONTEND_PORT || 5173);

const server = await createServer({
  root,
  configFile: false,
  clearScreen: false,
  plugins: [react()],
  optimizeDeps: {
    disabled: 'dev',
  },
  server: {
    host,
    port,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1200,
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
