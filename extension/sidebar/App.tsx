import React from 'react';
import ReactDOM from 'react-dom/client';
import Sidebar from './Sidebar';

const root = document.getElementById('sidebar-root');
if (root) {
    ReactDOM.createRoot(root).render(
        <React.StrictMode>
            <Sidebar />
        </React.StrictMode>,
    );
}

export default function App() {
    return <Sidebar />;
}
