import React from 'react';

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
    copied: boolean;
}

interface ErrorBoundaryProps {
    children: React.ReactNode;
}

export default class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null, copied: false };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error, copied: false };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        console.error('[ErrorBoundary] Caught render error:', error, info.componentStack);
    }

    private tryAgain = () => {
        this.setState({ hasError: false, error: null, copied: false });
    };

    private goHome = () => {
        window.location.href = '/chat';
    };

    private copyDetails = async () => {
        const err = this.state.error;
        if (!err) return;
        const text = `${err.message}\n\n${err.stack || ''}\n\nRoute: ${window.location.pathname}`;
        try {
            await navigator.clipboard.writeText(text);
            this.setState({ copied: true });
            setTimeout(() => this.setState({ copied: false }), 1500);
        } catch {
            // clipboard unavailable — silent
        }
    };

    render() {
        if (this.state.hasError) {
            const isDev = import.meta.env.DEV;
            const route = typeof window !== 'undefined' ? window.location.pathname : '';
            return (
                <div className="h-screen w-screen flex items-center justify-center bg-surface-0 p-6">
                    <div className="max-w-lg w-full rounded-card border border-accent-red/40 bg-surface-1 p-8 text-center">
                        <h1 className="text-xl font-semibold text-accent-red mb-2">Something went wrong</h1>
                        {route && (
                            <p className="mb-3 font-mono text-[11px] text-text-muted">
                                while rendering <span className="text-text-secondary">{route}</span>
                            </p>
                        )}
                        <p className="text-sm text-text-secondary mb-4">
                            Try again, or go back to chat. The error did not affect your saved data.
                        </p>
                        {isDev && this.state.error && (
                            <pre className="mb-5 text-left text-xs text-text-muted bg-surface-0 border border-surface-4 rounded-btn p-3 overflow-auto max-h-48 whitespace-pre-wrap">
                                {this.state.error.message}
                                {'\n'}
                                {this.state.error.stack}
                            </pre>
                        )}
                        <div className="flex flex-wrap items-center justify-center gap-2">
                            <button
                                type="button"
                                onClick={this.tryAgain}
                                className="px-4 py-2 rounded-btn border border-accent/40 bg-accent/10 text-accent text-sm hover:bg-accent/20 transition-colors"
                            >
                                Try again
                            </button>
                            <button
                                type="button"
                                onClick={this.goHome}
                                className="px-4 py-2 rounded-btn border border-surface-4 bg-surface-2 text-text-secondary text-sm hover:bg-surface-3 hover:text-text-primary transition-colors"
                            >
                                Go to chat
                            </button>
                            <button
                                type="button"
                                onClick={this.copyDetails}
                                className="px-4 py-2 rounded-btn border border-surface-4 bg-surface-2 text-text-muted text-sm hover:bg-surface-3 hover:text-text-secondary transition-colors"
                            >
                                {this.state.copied ? 'Copied' : 'Copy details'}
                            </button>
                            <button
                                type="button"
                                onClick={() => window.location.reload()}
                                className="px-4 py-2 rounded-btn border border-accent-red/40 bg-accent-red/10 text-accent-red text-sm hover:bg-accent-red/20 transition-colors"
                            >
                                Reload app
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
