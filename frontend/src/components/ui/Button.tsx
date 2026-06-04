import { forwardRef } from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'subtle' | 'danger' | 'success';
export type ButtonSize = 'sm' | 'md' | 'icon' | 'icon-sm';

/**
 * Shared button styling for the app. Press/focus/disabled states are handled
 * globally in index.css; this owns variant color and size only. Pass `className`
 * for layout (width, flex, margins) — not for overriding variant colors, since
 * `cn` does not resolve Tailwind conflicts.
 *
 * Every variant carries a 1px border (transparent where there is no visible
 * outline) so all buttons share the same box height and line up with inputs.
 */
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
    primary: 'border border-transparent bg-accent text-white shadow-elevation-1 hover:bg-accent-hover',
    secondary: 'border border-surface-4 bg-surface-2 text-text-primary hover:bg-surface-3',
    ghost: 'border border-transparent text-text-secondary hover:bg-surface-2 hover:text-text-primary',
    subtle: 'border border-accent/30 bg-accent/10 text-accent hover:bg-accent/20',
    danger: 'border border-accent-red/40 bg-accent-red/10 text-accent-red hover:bg-accent-red/20',
    success: 'border border-accent-green/40 bg-accent-green/10 text-accent-green hover:bg-accent-green/20',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
    sm: 'gap-1.5 px-2.5 py-1 text-xs',
    md: 'gap-2 px-3 py-1.5 text-sm',
    icon: 'p-1.5',
    'icon-sm': 'p-1',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
    { variant = 'secondary', size = 'md', className, type = 'button', ...props },
    ref,
) {
    return (
        <button
            ref={ref}
            type={type}
            className={cn(
                'inline-flex select-none items-center justify-center whitespace-nowrap rounded-btn font-medium tracking-tight',
                VARIANT_CLASSES[variant],
                SIZE_CLASSES[size],
                className,
            )}
            {...props}
        />
    );
});
