import { Loader2 } from 'lucide-react';

// `fill` renders into the parent's box (used as a content-area route fallback so the
// nav stays put); the default fills the viewport for the initial app load.
export default function LoadingScreen({ label = 'Loading jimAI…', fill = false }: { label?: string; fill?: boolean }) {
    return (
        <div className={`${fill ? 'h-full w-full' : 'h-dvh w-screen'} flex items-center justify-center bg-surface-0 text-text-secondary`}>
            <div className="flex items-center gap-3 text-sm animate-fade-in">
                <Loader2 size={16} className="animate-spin text-accent" />
                <span>{label}</span>
            </div>
        </div>
    );
}
