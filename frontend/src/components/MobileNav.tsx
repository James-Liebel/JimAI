import { NavLink } from 'react-router-dom';
import { GitPullRequest, Globe, MessageSquare, Settings, Hammer, Wrench, Bot, Sparkles } from 'lucide-react';
import { cn } from '../lib/utils';
import { prefetchRoute } from '../lib/routePrefetch';

const TABS = [
    { to: '/chat', label: 'Chat', icon: MessageSquare },
    { to: '/atlas', label: 'Atlas', icon: Globe },
    { to: '/builder', label: 'Builder', icon: Hammer },
    { to: '/agents', label: 'Agents', icon: Bot },
    { to: '/self-code', label: 'SelfCode', icon: Wrench },
];

const QUICK_ACTIONS = [
    { to: '/workflow', label: 'Review', icon: GitPullRequest },
    { to: '/skills', label: 'Skills', icon: Sparkles },
    { to: '/settings', label: 'Settings', icon: Settings },
];

export default function MobileNav() {
    return (
        <nav
            className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-surface-5 bg-surface-1 md:hidden"
            style={{ paddingBottom: 'var(--mobile-nav-pad)' }}
        >
            {TABS.map(({ to, label, icon: Icon }) => (
                <NavLink
                    key={to}
                    to={to}
                    onTouchStart={() => prefetchRoute(to)}
                    onMouseEnter={() => prefetchRoute(to)}
                    className={({ isActive }) =>
                        cn(
                            'relative flex min-h-[60px] flex-1 flex-col items-center justify-center gap-1 px-1 py-2.5 text-[10px] font-medium tracking-wide transition-colors duration-150',
                            'before:absolute before:inset-x-3 before:top-0 before:h-[2px] before:rounded-b-full before:bg-accent before:transition-opacity before:duration-200',
                            isActive ? 'text-accent before:opacity-100' : 'text-text-muted hover:text-text-secondary before:opacity-0',
                        )
                    }
                >
                    <Icon size={19} />
                    <span>{label}</span>
                </NavLink>
            ))}
            <div className="my-2 w-px self-stretch bg-surface-4" />
            {QUICK_ACTIONS.map(({ to, label, icon: Icon }) => (
                <NavLink
                    key={to}
                    to={to}
                    onTouchStart={() => prefetchRoute(to)}
                    onMouseEnter={() => prefetchRoute(to)}
                    className={({ isActive }) =>
                        cn(
                            'relative flex min-h-[60px] flex-1 flex-col items-center justify-center gap-1 px-1 py-2.5 text-[10px] font-medium tracking-wide transition-colors duration-150',
                            'before:absolute before:inset-x-3 before:top-0 before:h-[2px] before:rounded-b-full before:bg-accent before:transition-opacity before:duration-200',
                            isActive ? 'text-accent before:opacity-100' : 'text-text-muted hover:text-text-secondary before:opacity-0',
                        )
                    }
                >
                    <Icon size={19} />
                    <span>{label}</span>
                </NavLink>
            ))}
        </nav>
    );
}
