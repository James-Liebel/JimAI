import React, { useEffect, useState } from 'react';
import { DEFAULT_SETTINGS, JimAISettings, loadSettings, saveSettings, clearHistory } from './lib/storage';
import { checkHealth, setSpeedMode } from './lib/api';

const styles: Record<string, React.CSSProperties> = {
    container: { padding: '14px 14px 24px', display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto', height: '100%' },
    section: { display: 'flex', flexDirection: 'column', gap: '6px' },
    label: { fontSize: '11px', color: '#7070a0', textTransform: 'uppercase', letterSpacing: '0.06em' },
    input: {
        background: '#111114', border: '1px solid #1e1e24', color: '#e8e8f0',
        borderRadius: '6px', padding: '8px 10px', fontSize: '12px', outline: 'none',
    },
    row: { display: 'flex', gap: '6px' },
    btn: {
        flex: 1, padding: '7px 10px', background: '#111114', border: '1px solid #1e1e24',
        color: '#e8e8f0', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
    },
    btnActive: { background: '#3B82F6', border: '1px solid #3B82F6', color: 'white' },
    primary: {
        padding: '8px 12px', background: '#3B82F6', border: '1px solid #3B82F6',
        color: 'white', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', fontWeight: 600,
    },
    danger: {
        padding: '8px 12px', background: 'transparent', border: '1px solid #EF4444',
        color: '#EF4444', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
    },
    status: { fontSize: '11px', padding: '8px 10px', borderRadius: '6px' },
    ok: { background: 'rgba(34, 197, 94, 0.10)', color: '#22C55E', border: '1px solid rgba(34, 197, 94, 0.25)' },
    bad: { background: 'rgba(239, 68, 68, 0.10)', color: '#EF4444', border: '1px solid rgba(239, 68, 68, 0.25)' },
};

const SPEED_MODES: Array<JimAISettings['speedMode']> = ['fast', 'balanced', 'deep'];

export default function Settings() {
    const [settings, setSettings] = useState<JimAISettings>(DEFAULT_SETTINGS);
    const [loaded, setLoaded] = useState(false);
    const [test, setTest] = useState<{ ok: boolean; msg: string } | null>(null);
    const [savedAt, setSavedAt] = useState<number | null>(null);

    useEffect(() => {
        loadSettings().then((s) => {
            setSettings(s);
            setLoaded(true);
        });
    }, []);

    const update = async (patch: Partial<JimAISettings>) => {
        const next = { ...settings, ...patch };
        setSettings(next);
        await saveSettings(next);
        setSavedAt(Date.now());
    };

    const onPickSpeed = async (mode: JimAISettings['speedMode']) => {
        await update({ speedMode: mode });
        try {
            await setSpeedMode(mode, settings.backendUrl);
        } catch {
            /* surfaced via test connection */
        }
    };

    const onTest = async () => {
        setTest(null);
        const result = await checkHealth(settings.backendUrl);
        setTest({
            ok: result.ok,
            msg: result.ok ? 'Backend reachable, Ollama healthy.' : `Unreachable: ${result.details || 'unknown error'}`,
        });
    };

    const onClearHistory = async () => {
        await clearHistory();
        setSavedAt(Date.now());
    };

    if (!loaded) return <div style={{ padding: 14, color: '#7070a0', fontSize: 12 }}>Loading settings…</div>;

    return (
        <div style={styles.container}>
            <div style={styles.section}>
                <span style={styles.label}>Backend URL</span>
                <input
                    style={styles.input}
                    value={settings.backendUrl}
                    onChange={(e) => setSettings({ ...settings, backendUrl: e.target.value })}
                    onBlur={() => update({ backendUrl: settings.backendUrl })}
                    placeholder="http://localhost:8000"
                    spellCheck={false}
                />
            </div>

            <div style={styles.section}>
                <span style={styles.label}>Speed Mode</span>
                <div style={styles.row}>
                    {SPEED_MODES.map((mode) => (
                        <button
                            key={mode}
                            onClick={() => onPickSpeed(mode)}
                            style={{ ...styles.btn, ...(settings.speedMode === mode ? styles.btnActive : {}) }}
                        >
                            {mode}
                        </button>
                    ))}
                </div>
            </div>

            <div style={styles.section}>
                <span style={styles.label}>Diagnostics</span>
                <button style={styles.primary} onClick={onTest}>Test connection</button>
                {test && (
                    <div style={{ ...styles.status, ...(test.ok ? styles.ok : styles.bad) }}>
                        {test.msg}
                    </div>
                )}
            </div>

            <div style={styles.section}>
                <span style={styles.label}>History</span>
                <button style={styles.danger} onClick={onClearHistory}>Clear chat history</button>
            </div>

            <div style={{ fontSize: 10, color: '#55556A', marginTop: 'auto' }}>
                JimAI extension · settings auto-save{savedAt ? ' · saved' : ''}
            </div>
        </div>
    );
}
