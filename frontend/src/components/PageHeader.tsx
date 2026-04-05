import type { ReactNode } from 'react';
import { cn } from '../lib/utils';

/**
 * Standard page title + optional description and actions (design-system header).
 * `embedded`: use inside a card/panel (no bottom rule, tighter spacing).
 */
export function PageHeader({
    title,
    description,
    meta,
    actions,
    className,
    variant = 'default',
}: {
    title: string;
    description?: string;
    meta?: ReactNode;
    actions?: ReactNode;
    className?: string;
    variant?: 'default' | 'embedded';
}) {
    return (
        <header
            className={cn(
                variant === 'embedded' ? 'pb-4' : 'border-b border-surface-5 pb-5',
                className,
            )}
        >
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 space-y-1.5">
                    <h1 className="text-xl font-semibold tracking-tight text-text-primary">{title}</h1>
                    {description ? (
                        <p className="max-w-2xl text-sm leading-relaxed text-text-secondary">{description}</p>
                    ) : null}
                    {meta ? (
                        <div className="font-mono text-[11px] text-text-muted">{meta}</div>
                    ) : null}
                </div>
                {actions ? (
                    <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
                ) : null}
            </div>
        </header>
    );
}

/**
 * Card-style section with consistent title + body spacing.
 */
export function PageSection({
    title,
    children,
    className,
    bodyClassName,
}: {
    title: string;
    children: ReactNode;
    className?: string;
    bodyClassName?: string;
}) {
    return (
        <section className={cn('rounded-card border border-surface-4 bg-surface-1 p-5 md:p-6', className)}>
            <h2 className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">{title}</h2>
            <div className={cn('mt-4', bodyClassName)}>{children}</div>
        </section>
    );
}
