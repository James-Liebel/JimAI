import { NavLink } from 'react-router-dom';
import { GitPullRequest, MessageSquare, Settings, Hammer, Wrench, Workflow } from 'lucide-react';
import { cn } from '../lib/utils';

const TABS = [
    { to: '/chat', label: 'Chat', icon: MessageSquare },
    { to: '/builder', label: 'Build', icon: Hammer },
    { to: '/automation', label: 'Automate', icon: Workflow },
    { to: '/self-code', label: 'Improve', icon: Wrench },
];

const QUICK_ACTIONS = [
    { to: '/workflow', label: 'Review', icon: GitPullRequest },
    { to: '/settings', label: 'Settings', icon: Settings },
];

export default function MobileNav() {
    return (
        <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around bg-surface-1 border-t border-surface-3 md:hidden"
            style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
        >
            {TABS.map(({ to, label, icon: Icon }) => (
                <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                        cn(
                            'flex flex-col items-center gap-0.5 py-2 px-3 text-[11px] font-medium transition-colors min-h-[56px] justify-center flex-1',
                            isActive
                                ? 'text-accent'
                                : 'text-text-secondary',
                        )
                    }
                >
                    <Icon size={20} />
                    <span>{label}</span>
                </NavLink>
            ))}
            <div className="w-px self-stretch bg-surface-3 my-2" />
            {QUICK_ACTIONS.map(({ to, label, icon: Icon }) => (
                <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                        cn(
                            'flex flex-col items-center gap-0.5 py-2 px-2 text-[11px] font-medium transition-colors min-h-[56px] justify-center',
                            isActive ? 'text-accent' : 'text-text-secondary',
                        )
                    }
                >
                    <Icon size={18} />
                    <span>{label}</span>
                </NavLink>
            ))}
        </nav>
    );
}
