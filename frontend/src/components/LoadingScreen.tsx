import { Loader2 } from 'lucide-react';

export default function LoadingScreen({ label = 'Loading jimAI…' }: { label?: string }) {
    return (
        <div className="h-screen w-screen flex items-center justify-center bg-surface-0 text-text-secondary">
            <div className="flex items-center gap-3 text-sm">
                <Loader2 size={16} className="animate-spin text-accent" />
                <span>{label}</span>
            </div>
        </div>
    );
}
