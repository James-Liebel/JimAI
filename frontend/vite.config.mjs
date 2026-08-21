import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Stamped into the bundle as __BUILD_ID__ and written to dist/build-id.json. A
// running tab compares the two to tell whether the server is on a newer build
// than the one it booted from — see components/UpdateBanner.tsx.
const BUILD_ID = new Date().toISOString();

function emitBuildId() {
    return {
        name: 'jimai-build-id',
        generateBundle() {
            this.emitFile({
                type: 'asset',
                fileName: 'build-id.json',
                source: JSON.stringify({ id: BUILD_ID }),
            });
        },
    };
}

// Split heavy third-party libs into their own chunks so:
//   1. The initial route only loads what it needs (react + router + app shell).
//   2. Heavy deps (markdown/katex/syntax-highlighter/monaco/reactflow) cache across deploys.
// The result: faster first paint and cheaper subsequent navigations.
export default defineConfig({
    plugins: [react(), emitBuildId()],
    define: { __BUILD_ID__: JSON.stringify(BUILD_ID) },
    server: {
        host: '0.0.0.0',
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/health': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: 'dist',
        chunkSizeWarningLimit: 1200,
        target: 'es2022',
        cssCodeSplit: true,
        sourcemap: false,
        reportCompressedSize: false,
        rollupOptions: {
            output: {
                manualChunks(id) {
                    if (!id.includes('node_modules')) return undefined;
                    if (
                        id.includes('react-syntax-highlighter') ||
                        id.includes('refractor') ||
                        id.includes('highlight.js') ||
                        id.includes('lowlight')
                    ) {
                        return 'vendor-syntax';
                    }
                    if (
                        id.includes('react-markdown') ||
                        id.includes('remark') ||
                        id.includes('rehype') ||
                        id.includes('micromark') ||
                        id.includes('mdast') ||
                        id.includes('unified') ||
                        id.includes('hast') ||
                        id.includes('unist')
                    ) {
                        return 'vendor-markdown';
                    }
                    if (id.includes('katex')) return 'vendor-katex';
                    if (id.includes('monaco')) return 'vendor-monaco';
                    if (id.includes('reactflow') || id.includes('@reactflow')) return 'vendor-reactflow';
                    if (id.includes('react-router')) return 'vendor-router';
                    if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/') || id.includes('scheduler')) {
                        return 'vendor-react';
                    }
                    if (id.includes('@radix-ui')) return 'vendor-radix';
                    if (id.includes('lucide-react')) return 'vendor-icons';
                    return undefined;
                },
            },
        },
    },
});
