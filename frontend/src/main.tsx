import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';

const Chat = lazy(() => import('./pages/Chat'));
const Notebook = lazy(() => import('./pages/Notebook'));
const AgentStudio = lazy(() => import('./pages/AgentStudio'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const WorkflowReview = lazy(() => import('./pages/WorkflowReview'));
const Research = lazy(() => import('./pages/Research'));
const SelfCode = lazy(() => import('./pages/SelfCode'));
const Settings = lazy(() => import('./pages/Settings'));
const AgentBrowser = lazy(() => import('./pages/AgentBrowser'));
const Builder = lazy(() => import('./pages/Builder'));
const SystemAudit = lazy(() => import('./pages/SystemAudit'));
const Automation = lazy(() => import('./pages/Automation'));

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
                        <Route path="/workflow" element={<WorkflowReview />} />
                        <Route path="/research" element={<Research />} />
                        <Route path="/browser" element={<AgentBrowser />} />
                        <Route path="/builder" element={<Builder />} />
                        <Route path="/automation" element={<Automation />} />
                        <Route path="/self-code" element={<SelfCode />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="/audit" element={<SystemAudit />} />
                        <Route path="/notebook" element={<Notebook />} />
                        <Route path="/agents" element={<AgentStudio />} />
                    </Route>
                </Routes>
            </Suspense>
        </BrowserRouter>
        </ErrorBoundary>
    </React.StrictMode>,
);

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(err => {
            console.warn('Service worker registration failed:', err);
        });
    });
}
