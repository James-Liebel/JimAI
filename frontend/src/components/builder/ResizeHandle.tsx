import { useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';

type Axis = 'horizontal' | 'vertical';

/**
 * Drag to resize adjacent panels. `onDelta` receives movementX (vertical bar) or movementY (horizontal bar).
 */
export function ResizeHandle({
    axis,
    onDelta,
    onCommit,
    className,
}: {
    axis: Axis;
    onDelta: (delta: number) => void;
    onCommit?: () => void;
    className?: string;
}) {
    const dragging = useRef(false);

    useEffect(() => {
        const onMove = (ev: MouseEvent) => {
            if (!dragging.current) return;
            onDelta(axis === 'horizontal' ? ev.movementX : ev.movementY);
        };
        const onUp = () => {
            if (dragging.current) onCommit?.();
            dragging.current = false;
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        return () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
    }, [axis, onDelta, onCommit]);

    return (
        <div
            role="separator"
            aria-orientation={axis === 'horizontal' ? 'vertical' : 'horizontal'}
            onMouseDown={() => {
                dragging.current = true;
            }}
            className={cn(
                'shrink-0 select-none bg-transparent hover:bg-accent/30',
                axis === 'horizontal' ? 'w-1 cursor-col-resize' : 'h-1.5 cursor-row-resize',
                className,
            )}
        />
    );
}
