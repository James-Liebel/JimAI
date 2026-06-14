import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
import LoadingScreen from './components/LoadingScreen';
import { prefetchRoute } from './lib/routePrefetch';
// Self-hosted webfonts (bundled woff2 — no external egress, instant offline cold
// start). Weights mirror the former Google Fonts request: Outfit 400–700,
// JetBrains Mono 400–600.
import '@fontsource/outfit/400.css';
import '@fontsource/outfit/500.css';
import '@fontsource/outfit/600.css';
import '@fontsource/outfit/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/jetbrains-mono/600.css';
import './index.css';

const SERVICE_WORKER_VERSION = '2026-06-14-1';

// Chat is the default landing route — keep a reference to its dynamic import so
// we can warm it on requestIdleCallback before the user clicks anything.
const importChat = () => import('./pages/Chat');
const Chat = lazy(importChat);
const Notebook = lazy(() => import('./pages/Notebook'));
const AgentStudio = lazy(() => import('./pages/AgentStudio'));
const Agents = lazy(() => import('./pages/Agents'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const WorkflowReview = lazy(() => import('./pages/WorkflowReview'));
const Research = lazy(() => import('./pages/Research'));
const SelfCode = lazy(() => import('./pages/SelfCode'));
const Settings = lazy(() => import('./pages/Settings'));
const AgentBrowser = lazy(() => import('./pages/AgentBrowser'));
const Atlas = lazy(() => import('./pages/Atlas'));
const Builder = lazy(() => import('./pages/Builder'));
const SystemAudit = lazy(() => import('./pages/SystemAudit'));
const Automation = lazy(() => import('./pages/Automation'));
const Skills = lazy(() => import('./pages/Skills'));
const Autonomy = lazy(() => import('./pages/Autonomy'));
const Security = lazy(() => import('./pages/Security'));

async function clearExistingServiceWorkersForDev(): Promise<void> {
    if (!('serviceWorker' in navigator)) return;
    try {
        const registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.map((registration) => registration.unregister()));
        if ('caches' in window) {
            const keys = await caches.keys();
            await Promise.all(
                keys
                    .filter((key) => key.startsWith('private-ai-') || key.startsWith('jimai-'))
                    .map((key) => caches.delete(key)),
            );
        }
    } catch (err) {
        console.warn('Service worker cleanup failed:', err);
    }
}

async function setupServiceWorker(): Promise<void> {
    if (!('serviceWorker' in navigator)) return;
    if (import.meta.env.DEV) {
        await clearExistingServiceWorkersForDev();
        return;
    }
    try {
        await navigator.serviceWorker.register(`/sw.js?v=${SERVICE_WORKER_VERSION}`);
    } catch (err) {
        console.warn('Service worker registration failed:', err);
    }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ErrorBoundary>
        <BrowserRouter>
            <Suspense fallback={<LoadingScreen />}>
                <Routes>
                    <Route element={<AppLayout />}>
                        <Route path="/" element={<Navigate to="/chat" replace />} />
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/chat" element={<Chat />} />
                        <Route path="/skills" element={<Skills />} />
                        <Route path="/autonomy" element={<Autonomy />} />
                        <Route path="/security" element={<Security />} />
                        <Route path="/workflow" element={<WorkflowReview />} />
                        <Route path="/research" element={<Research />} />
                        <Route path="/browser" element={<AgentBrowser />} />
                        <Route path="/atlas" element={<Atlas />} />
                        <Route path="/builder" element={<Builder />} />
                        <Route path="/automation" element={<Automation />} />
                        <Route path="/system" element={<Navigate to="/chat" replace />} />
                        <Route path="/self-code" element={<SelfCode />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="/audit" element={<SystemAudit />} />
                        <Route path="/notebook" element={<Notebook />} />
                        <Route path="/agents" element={<Agents />} />
                        <Route path="/agent-studio" element={<AgentStudio />} />
                        {/* Unknown URLs fall back to chat instead of a blank content area. */}
                        <Route path="*" element={<Navigate to="/chat" replace />} />
                    </Route>
                </Routes>
            </Suspense>
        </BrowserRouter>
        </ErrorBoundary>
    </React.StrictMode>,
);

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        void setupServiceWorker();
    });
}

// Prefetch the default route's chunk + its heaviest dependency (MessageBubble)
// during idle time so the first chat render does not pay the lazy-load cost.
const idle: (cb: () => void) => void =
    typeof (window as any).requestIdleCallback === 'function'
        ? (cb) => (window as any).requestIdleCallback(cb, { timeout: 2000 })
        : (cb) => window.setTimeout(cb, 200);
idle(() => {
    void importChat();
    void import('./components/MessageBubble');
    // Then warm the rest of the primary tabs in the background, so switching to
    // any of them is instant instead of paying the lazy-chunk fetch on click.
    idle(() => {
        ['/atlas', '/builder', '/agents', '/self-code', '/workflow', '/skills', '/settings'].forEach(prefetchRoute);
    });
});
