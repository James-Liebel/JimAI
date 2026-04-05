import { NavLink } from 'react-router-dom';
import { GitPullRequest, MessageSquare, Settings, Hammer, Wrench, Workflow, Bot } from 'lucide-react';
import { cn } from '../lib/utils';

const TABS = [
    { to: '/chat', label: 'Chat', icon: MessageSquare },
    { to: '/builder', label: 'Builder', icon: Hammer },
    { to: '/agents', label: 'Agents', icon: Bot },
    { to: '/automation', label: 'Automation', icon: Workflow },
    { to: '/self-code', label: 'SelfCode', icon: Wrench },
];

const QUICK_ACTIONS = [
    { to: '/workflow', label: 'Review', icon: GitPullRequest },
    { to: '/settings', label: 'Settings', icon: Settings },
];

export default function MobileNav() {
    return (
        <nav
            className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-surface-5 bg-surface-1 md:hidden"
            style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
        >
            {TABS.map(({ to, label, icon: Icon }) => (
                <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                        cn(
                            'flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 px-2 py-2 text-[10px] font-medium tracking-wide transition-colors duration-150',
                            isActive ? 'text-accent' : 'text-text-muted hover:text-text-secondary',
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
                    className={({ isActive }) =>
                        cn(
                            'flex min-h-[52px] flex-col items-center justify-center gap-0.5 px-2 py-2 text-[10px] font-medium tracking-wide transition-colors duration-150',
                            isActive ? 'text-accent' : 'text-text-muted hover:text-text-secondary',
                        )
                    }
                >
                    <Icon size={17} />
                    <span>{label}</span>
                </NavLink>
            ))}
        </nav>
    );
}
