import type { Mode } from '../lib/types';
import { cn } from '../lib/utils';

const MODES: { key: Mode; label: string; shortcut: string; icon: string }[] = [
    { key: 'math', label: 'Math', shortcut: 'Alt+1', icon: '∑' },
    { key: 'code', label: 'Code', shortcut: 'Alt+2', icon: '⟨/⟩' },
    { key: 'chat', label: 'Chat', shortcut: 'Alt+3', icon: '💬' },
    { key: 'vision', label: 'Vision', shortcut: 'Alt+4', icon: '👁' },
    { key: 'writing', label: 'Writing', shortcut: 'Alt+5', icon: '✍' },
];

const MODE_COLORS: Record<Mode, string> = {
    math: 'from-violet-500 to-purple-600',
    code: 'from-emerald-500 to-teal-600',
    chat: 'from-blue-500 to-indigo-600',
    vision: 'from-amber-500 to-orange-600',
    writing: 'from-rose-500 to-pink-600',
    data: 'from-cyan-500 to-sky-600',
    finance: 'from-lime-500 to-green-600',
};

interface Props {
    active: Mode;
    onChange: (mode: Mode) => void;
}

export default function ModeSelector({ active, onChange }: Props) {
    return (
        <div className="flex items-center gap-1 p-1 bg-surface-2 rounded-none">
            {MODES.map(({ key, label, shortcut, icon }) => (
                <button
                    key={key}
                    id={`mode-${key}`}
                    onClick={() => onChange(key)}
                    title={shortcut}
                    className={cn(
                        'relative px-3 py-1.5 rounded-none text-sm font-medium transition-all duration-200',
                        'hover:bg-surface-3',
                        active === key
                            ? `bg-gradient-to-r ${MODE_COLORS[key]} text-white shadow-none shadow-accent/20`
                            : 'text-text-secondary hover:text-text-primary',
                    )}
                >
                    <span className="mr-1.5">{icon}</span>
                    {label}
                    <span className="ml-1.5 text-[10px] opacity-50 hidden lg:inline">
                        {shortcut}
                    </span>
                </button>
            ))}
        </div>
    );
}
