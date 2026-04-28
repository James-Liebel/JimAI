export interface StoredMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
}

export interface JimAISettings {
    backendUrl: string;
    speedMode: 'fast' | 'balanced' | 'deep';
}

export const DEFAULT_SETTINGS: JimAISettings = {
    backendUrl: 'http://localhost:8000',
    speedMode: 'balanced',
};

const SETTINGS_KEY = 'jimai_settings';
const HISTORY_KEY = 'jimai_history';
const HISTORY_LIMIT = 200;

export async function loadSettings(): Promise<JimAISettings> {
    const result = await chrome.storage.local.get(SETTINGS_KEY);
    const stored = result[SETTINGS_KEY] as Partial<JimAISettings> | undefined;
    return { ...DEFAULT_SETTINGS, ...(stored || {}) };
}

export async function saveSettings(settings: JimAISettings): Promise<void> {
    await chrome.storage.local.set({ [SETTINGS_KEY]: settings });
}

export async function loadHistory(): Promise<StoredMessage[]> {
    const result = await chrome.storage.local.get(HISTORY_KEY);
    const stored = result[HISTORY_KEY];
    return Array.isArray(stored) ? (stored as StoredMessage[]) : [];
}

export async function saveHistory(history: StoredMessage[]): Promise<void> {
    const trimmed = history.slice(-HISTORY_LIMIT);
    await chrome.storage.local.set({ [HISTORY_KEY]: trimmed });
}

export async function clearHistory(): Promise<void> {
    await chrome.storage.local.remove(HISTORY_KEY);
}

export function onSettingsChanged(cb: (settings: JimAISettings) => void): () => void {
    const handler = (changes: { [key: string]: chrome.storage.StorageChange }, area: string) => {
        if (area === 'local' && changes[SETTINGS_KEY]) {
            cb({ ...DEFAULT_SETTINGS, ...(changes[SETTINGS_KEY].newValue || {}) });
        }
    };
    chrome.storage.onChanged.addListener(handler);
    return () => chrome.storage.onChanged.removeListener(handler);
}
