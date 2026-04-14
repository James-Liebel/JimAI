import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';

const SERVICE_WORKER_VERSION = '2026-03-22-1';

const Chat = lazy(() => import('./pages/Chat'));
const Notebook = lazy(() => import('./pages/Notebook'));
const AgentStudio = lazy(() => import('./pages/AgentStudio'));
const Agents = lazy(() => import('./pages/Agents'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const WorkflowReview = lazy(() => import('./pages/WorkflowReview'));
const Research = lazy(() => import('./pages/Research'));
const SelfCode = lazy(() => import('./pages/SelfCode'));
const Settings = lazy(() => import('./pages/Settings'));
const AgentBrowser = lazy(() => import('./pages/AgentBrowser'));
const BrowserAtlas = lazy(() => import('./pages/BrowserAtlas'));
const Builder = lazy(() => import('./pages/Builder'));
const SystemAudit = lazy(() => import('./pages/SystemAudit'));
const Automation = lazy(() => import('./pages/Automation'));
const Skills = lazy(() => import('./pages/Skills'));

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
            <Suspense
                fallback={
                    <div className="h-screen w-screen flex items-center justify-center bg-surface-0 text-text-secondary text-sm">
                        Loading jimAI...
                    </div>
                }
            >
                <Routes>
                    <Route element={<AppLayout />}>
                        <Route path="/" element={<Navigate to="/chat" replace />} />
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/chat" element={<Chat />} />
                        <Route path="/skills" element={<Skills />} />
                        <Route path="/workflow" element={<WorkflowReview />} />
                        <Route path="/research" element={<Research />} />
                        <Route path="/browser" element={<AgentBrowser />} />
                        <Route path="/atlas" element={<BrowserAtlas />} />
                        <Route path="/builder" element={<Builder />} />
                        <Route path="/automation" element={<Automation />} />
                        <Route path="/system" element={<Navigate to="/chat" replace />} />
                        <Route path="/self-code" element={<SelfCode />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="/audit" element={<SystemAudit />} />
                        <Route path="/notebook" element={<Notebook />} />
                        <Route path="/agents" element={<Agents />} />
                        <Route path="/agent-studio" element={<AgentStudio />} />
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
