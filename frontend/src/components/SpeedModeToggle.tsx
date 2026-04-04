import { useState } from 'react';
import type { SpeedMode } from '../lib/types';
import { cn } from '../lib/utils';
import { useMediaQuery } from '../hooks/useMediaQuery';

interface Props {
    currentMode: SpeedMode;
    onModeChange: (mode: SpeedMode) => void;
}

const MODES: { value: SpeedMode; icon: string; label: string; color: string; tooltip: string }[] = [
    {
        value: 'fast',
        icon: '⚡',
        label: 'Fast',
        color: 'text-accent bg-accent/15 border-accent/30',
        tooltip: 'Uses smaller, faster models. Best for quick Q&A.',
    },
    {
        value: 'balanced',
        icon: '◎',
        label: 'Balanced',
        color: 'text-accent bg-accent/15 border-accent/30',
        tooltip: 'Balanced speed and quality. Recommended for most tasks.',
    },
    {
        value: 'deep',
        icon: '🔬',
        label: 'Deep',
        color: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
        tooltip: 'Uses largest models with extended reasoning. Best for complex tasks.',
    },
];

export default function SpeedModeToggle({ currentMode, onModeChange }: Props) {
    const isMobile = useMediaQuery('(max-width: 768px)');
    const [hoveredMode, setHoveredMode] = useState<SpeedMode | null>(null);

    return (
        <div className="relative flex items-center">
            <div className="flex items-center bg-surface-0 rounded-none p-0.5 border border-surface-4">
                {MODES.map((m) => {
                    const isActive = currentMode === m.value;
                    return (
                        <button
                            key={m.value}
                            onClick={() => onModeChange(m.value)}
                            onMouseEnter={() => setHoveredMode(m.value)}
                            onMouseLeave={() => setHoveredMode(null)}
                            className={cn(
                                'relative rounded transition-all text-xs font-medium',
                                isMobile ? 'px-2 py-1.5' : 'px-2.5 py-1',
                                isActive
                                    ? m.color
                                    : 'text-text-muted hover:text-text-secondary hover:bg-surface-2',
                            )}
                            title={m.tooltip}
                        >
                            <span className="mr-1">{m.icon}</span>
                            {!isMobile && m.label}
                        </button>
                    );
                })}
            </div>

            {!isMobile && hoveredMode && (
                <div className="absolute top-full right-0 mt-1.5 w-56 p-2 bg-surface-3 border border-surface-4 rounded-none shadow-none z-50 text-[11px] text-text-secondary animate-fade-in pointer-events-none">
                    {MODES.find((m) => m.value === hoveredMode)?.tooltip}
                </div>
            )}
        </div>
    );
}
