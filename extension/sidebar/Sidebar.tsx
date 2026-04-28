import React, { useState } from 'react';
import Chat from './Chat';
import Page from './Page';
import Settings from './Settings';

type Tab = 'chat' | 'page' | 'settings';

const TABS: Array<{ id: Tab; label: string; emoji: string }> = [
    { id: 'chat',     label: 'Chat',     emoji: '💬' },
    { id: 'page',     label: 'Page',     emoji: '📄' },
    { id: 'settings', label: 'Settings', emoji: '⚙️' },
];

const styles: Record<string, React.CSSProperties> = {
    root: {
        height: '100vh', display: 'flex', flexDirection: 'column',
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
        color: '#e8e8f0', background: '#0a0a0c',
    },
    header: {
        padding: '8px 12px', borderBottom: '1px solid #1e1e24',
        display: 'flex', alignItems: 'center', gap: '8px',
    },
    title: { fontWeight: 700, fontSize: '13px', letterSpacing: '0.02em' },
    sub: { fontSize: '10px', color: '#55556A' },
    tabs: {
        display: 'flex', gap: '0', borderBottom: '1px solid #1e1e24',
        background: '#0a0a0c',
    },
    tab: {
        flex: 1, padding: '8px 6px', fontSize: '11px', fontWeight: 500,
        background: 'transparent', border: 'none', color: '#7070a0',
        cursor: 'pointer', borderBottom: '2px solid transparent',
        transition: 'color 120ms, border-color 120ms',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px',
    },
    tabActive: { color: '#e8e8f0', borderBottomColor: '#3B82F6' },
    body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' },
};

export default function Sidebar() {
    const [active, setActive] = useState<Tab>('chat');

    return (
        <div style={styles.root}>
            <div style={styles.header}>
                <div style={{
                    width: 22, height: 22, borderRadius: 6, background: 'rgba(59,130,246,0.12)',
                    border: '1px solid rgba(59,130,246,0.35)', color: '#3B82F6',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 10, fontWeight: 700,
                }}>jA</div>
                <span style={styles.title}>JimAI</span>
                <span style={styles.sub}>· local</span>
            </div>
            <div style={styles.tabs} role="tablist">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        role="tab"
                        aria-selected={active === t.id}
                        onClick={() => setActive(t.id)}
                        style={{ ...styles.tab, ...(active === t.id ? styles.tabActive : {}) }}
                    >
                        <span>{t.emoji}</span>
                        <span>{t.label}</span>
                    </button>
                ))}
            </div>
            <div style={styles.body}>
                {active === 'chat' && <Chat />}
                {active === 'page' && <Page />}
                {active === 'settings' && <Settings />}
            </div>
        </div>
    );
}
