import React from 'react';
import ReactDOM from 'react-dom/client';
import Chat from './Chat';

const root = document.getElementById('sidebar-root');
if (root) {
    ReactDOM.createRoot(root).render(
        <React.StrictMode>
            <Chat />
        </React.StrictMode>
    );
}

export default function App() {
    return <Chat />;
}
